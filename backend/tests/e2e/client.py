"""
Tiny HTTP client and check recorder for the end-to-end suites. Standard
library only, so the suites run with any Python 3.9+ on the host.
"""
from __future__ import annotations

import http.cookiejar
import json
import subprocess
import urllib.error
import urllib.request
import uuid
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
SAMPLES = REPO / "sample-docs"
JOB_SAMPLES = SAMPLES / "job-2025-118"

# Named test accounts. They only ever exist on the throwaway e2e stack.
OWNER = ("suriya@tenext.in", "e2e-password-suriya", "Suriyakumar Vijayanayagam")
REVIEWER = ("qa.reviewer@tenext.in", "e2e-password-reviewer", "QA Reviewer")


class Results:
    def __init__(self):
        self.failures: list[str] = []
        self.passed = 0

    def check(self, name: str, ok: bool, detail=None) -> bool:
        print(("PASS " if ok else "FAIL ") + name + (f"  -- {detail}" if detail is not None and not ok else ""))
        if ok:
            self.passed += 1
        else:
            self.failures.append(name)
        return ok


class Client:
    def __init__(self, base: str):
        self.base = base.rstrip("/")
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))

    def req(self, method: str, path: str, body=None, raw: bool = False, headers=None, timeout: int = 600):
        data, hdrs = None, dict(headers or {})
        if isinstance(body, bytes):
            data = body
        elif body is not None:
            data, hdrs["Content-Type"] = json.dumps(body).encode(), "application/json"
        request = urllib.request.Request(self.base + path, data=data, method=method, headers=hdrs)
        try:
            with self.opener.open(request, timeout=timeout) as response:
                payload = response.read()
                return response.status, (payload if raw else json.loads(payload or b"null")), response.headers
        except urllib.error.HTTPError as error:
            payload = error.read()
            try:
                return error.code, json.loads(payload), error.headers
            except Exception:
                return error.code, payload, error.headers

    def signin(self, account) -> int:
        """Registers the named account, or signs in if it already exists on this stack."""
        email, password, name = account
        status, _, _ = self.req("POST", "/api/auth/register", {"email": email, "password": password, "display_name": name})
        if status == 409:
            status, _, _ = self.req("POST", "/api/auth/login", {"email": email, "password": password})
        return status

    def upload(self, path: str, files, fields: dict | None = None):
        boundary = uuid.uuid4().hex
        parts = [f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode() for k, v in (fields or {}).items()]
        for file in files:
            parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"files\"; filename=\"{file.name}\"\r\n"
                         "Content-Type: application/octet-stream\r\n\r\n".encode() + file.read_bytes() + b"\r\n")
        body = b"".join(parts) + f"--{boundary}--\r\n".encode()
        return self.req("POST", path, body, headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})

    def ask(self, chat_id: str, content: str) -> list:
        """Sends a message and returns the server-sent events as (name, data) pairs."""
        _, raw, _ = self.req("POST", f"/api/chats/{chat_id}/messages", {"content": content}, raw=True)
        events = []
        for frame in raw.decode().split("\n\n"):
            name, data = None, ""
            for line in frame.split("\n"):
                if line.startswith("event:"):
                    name = line[6:].strip()
                elif line.startswith("data:"):
                    data += line[5:].strip()
            if name:
                events.append((name, json.loads(data)))
        return events

    def wait_ready(self, list_path: str, key: str = "documents", seconds: int = 300) -> list:
        import time
        deadline = time.time() + seconds
        while True:
            _, body, _ = self.req("GET", list_path)
            documents = body[key]
            if all(d["status"] in ("ready", "failed") for d in documents) or time.time() > deadline:
                return documents
            time.sleep(2)


def compose(project: str, *args: str) -> subprocess.CompletedProcess:
    """docker compose against the e2e project, from the repo root."""
    return subprocess.run(["docker", "compose", "-p", project, "-f", "compose.yaml", *args],
                          cwd=REPO, capture_output=True, text=True)
