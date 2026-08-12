"""
Persistent project memory - NOT the same thing as RAG.

RAG retrieves facts from documents on-demand. Memory is the running
understanding of a project: decisions made, entities discussed, standing
context ("the user cares about the power budget of block X"). It's a small,
curated, ever-growing summary re-injected into every prompt so nothing is
forgotten even after the context window would normally have dropped it.

Isolation follows the same (user_id, project_id) key everywhere else uses.
"""
import sqlite3
import time
from contextlib import contextmanager
from app.config import settings

_SCHEMA = """
CREATE TABLE IF NOT EXISTS memory_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    entry_type TEXT NOT NULL,      -- 'fact' | 'decision' | 'preference' | 'summary'
    content TEXT NOT NULL,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_memory_scope ON memory_entries(user_id, project_id);
"""


@contextmanager
def _conn():
    conn = sqlite3.connect(settings.memory_db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with _conn() as c:
        c.executescript(_SCHEMA)


def add_entry(user_id: str, project_id: str, entry_type: str, content: str):
    with _conn() as c:
        c.execute(
            "INSERT INTO memory_entries (user_id, project_id, entry_type, content, created_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, project_id, entry_type, content, time.time()),
        )


def get_project_memory(user_id: str, project_id: str, limit: int = 50) -> list[dict]:
    with _conn() as c:
        rows = c.execute(
            "SELECT entry_type, content, created_at FROM memory_entries "
            "WHERE user_id = ? AND project_id = ? ORDER BY created_at DESC LIMIT ?",
            (user_id, project_id, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def render_memory_block(user_id: str, project_id: str) -> str:
    """
    Condensed text block injected into the system prompt. Oldest-first so
    the narrative reads chronologically.
    """
    entries = get_project_memory(user_id, project_id)
    if not entries:
        return ""
    entries = list(reversed(entries))
    lines = [f"- [{e['entry_type']}] {e['content']}" for e in entries]
    return "Known project context (do not repeat this back verbatim, use it):\n" + "\n".join(lines)
