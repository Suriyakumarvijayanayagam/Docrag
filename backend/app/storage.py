"""
Files on disk that belong to a document: the uploaded original and any figure
images extracted from it. Database rows cascade on their own; these don't, so
every path that deletes a document (or the chat / knowledge base holding it)
must call remove_document_files.
"""
import hashlib
import mimetypes
import re
import shutil
from pathlib import Path
from uuid import uuid4

from psycopg.errors import UniqueViolation

from app.config import settings
from app.db import connection


def figure_dir(document_id) -> Path:
    return Path(settings.upload_dir) / "figures" / str(document_id)


def remove_document_files(document: dict) -> None:
    Path(document["storage_path"]).unlink(missing_ok=True)
    shutil.rmtree(figure_dir(document["id"]), ignore_errors=True)


def store_document(content: bytes, filename: str, content_type: str | None = None, *,
                   kb_id=None, chat_id=None, user_id=None) -> dict:
    """
    Saves an upload under a random name and queues it for indexing. Returns the
    new document row, or {"status": "duplicate", ...} when the library already
    holds an identical file. Callers validate type and size first.
    """
    digest = hashlib.sha256(content).hexdigest()
    if kb_id:
        with connection() as conn:
            duplicate = conn.execute(
                "SELECT id FROM documents WHERE knowledge_base_id=%s AND sha256=%s", (kb_id, digest)
            ).fetchone()
        if duplicate:
            return {"id": duplicate["id"], "filename": filename, "status": "duplicate"}

    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    document_id = uuid4()
    suffix = re.sub(r"[^a-zA-Z0-9.]", "", Path(filename).suffix.lower())
    storage_path = upload_dir / f"{document_id}{suffix}"
    storage_path.write_bytes(content)
    content_type = content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"
    try:
        with connection() as conn:
            row = conn.execute(
                """INSERT INTO documents(id,knowledge_base_id,conversation_id,uploaded_by,filename,content_type,
                   byte_size,sha256,storage_path) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
                (document_id, kb_id, chat_id, user_id, filename, content_type, len(content), digest, str(storage_path)),
            ).fetchone()
            conn.execute("INSERT INTO ingestion_jobs(document_id) VALUES(%s)", (document_id,))
            conn.commit()
        return row
    except UniqueViolation:
        # the same file landed in this library concurrently, after the check above
        storage_path.unlink(missing_ok=True)
        return {"id": None, "filename": filename, "status": "duplicate"}
    except Exception:
        storage_path.unlink(missing_ok=True)
        raise
