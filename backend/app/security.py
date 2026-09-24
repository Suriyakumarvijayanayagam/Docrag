import logging
import os
import secrets
import time
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import Depends, HTTPException, Request, status

from app.config import settings
from app.db import connection

logger = logging.getLogger("datum.security")
password_hasher = PasswordHasher()
ALGORITHM = "HS256"
COOKIE_NAME = "datum_session"
# Values that have shipped in .env.example or as defaults. Anyone can read
# them, so a token signed with one is forgeable.
_PUBLIC_SECRETS = {"", "development-only-change-me", "replace-with-a-long-random-secret", "change-me"}


@lru_cache(maxsize=1)
def jwt_secret() -> str:
    """
    The configured JWT_SECRET, unless it is missing, a published placeholder or
    too short - then a random secret generated once and kept next to the
    uploads, so sessions survive restarts without anyone having to set it.
    """
    configured = settings.jwt_secret.strip()
    if configured not in _PUBLIC_SECRETS and len(configured) >= 32:
        return configured
    path = Path(settings.upload_dir) / ".jwt_secret"
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        # another process may have created it and not finished writing yet
        for _ in range(50):
            existing = path.read_text().strip()
            if existing:
                return existing
            time.sleep(0.1)
        raise RuntimeError(f"{path} exists but is empty; delete it to generate a new secret")
    with os.fdopen(fd, "w") as handle:
        handle.write(secrets.token_urlsafe(48))
    if configured:
        logger.warning("JWT_SECRET is a placeholder or shorter than 32 characters; using a generated secret instead")
    return path.read_text().strip()


def hash_password(password: str) -> str:
    if len(password) < 10:
        raise HTTPException(status_code=400, detail="Password must be at least 10 characters")
    return password_hasher.hash(password)


def verify_password(password: str, encoded: str) -> bool:
    try:
        return password_hasher.verify(encoded, password)
    except VerifyMismatchError:
        return False


def create_token(user_id: str) -> str:
    expires = datetime.now(timezone.utc) + timedelta(hours=settings.jwt_expire_hours)
    return jwt.encode({"sub": user_id, "exp": expires}, jwt_secret(), algorithm=ALGORITHM)


def current_user(request: Request) -> dict:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sign in to continue")
    try:
        payload = jwt.decode(token, jwt_secret(), algorithms=[ALGORITHM])
        user_id = payload.get("sub")
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="Session expired. Sign in again.") from exc
    with connection() as conn:
        user = conn.execute(
            "SELECT id, email, display_name FROM users WHERE id = %s", (user_id,)
        ).fetchone()
    if not user:
        raise HTTPException(status_code=401, detail="Account no longer exists")
    return user


def require_kb_access(user_id: str, kb_id: str) -> dict:
    with connection() as conn:
        row = conn.execute(
            """SELECT kb.*, m.role FROM knowledge_bases kb
               JOIN kb_members m ON m.kb_id = kb.id
               WHERE kb.id = %s AND m.user_id = %s""",
            (kb_id, user_id),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    return row


User = Depends(current_user)
