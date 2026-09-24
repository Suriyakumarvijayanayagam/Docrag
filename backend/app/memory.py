"""
Knowledge-base memory - not the same thing as retrieval.

Retrieval answers "what do the documents say". Memory is the running
understanding built up in conversations: facts established, decisions made,
constraints stated. It is shared by everyone with access to the knowledge
base and injected into every prompt, so it survives across chats without a
growing transcript.

Each exchange is distilled by the model into one entry or nothing. Logging raw
questions instead makes the block mostly noise after a few dozen exchanges.
"""
import json
import logging
import re
import threading

from app import llm
from app.config import settings
from app.db import connection

logger = logging.getLogger("datum.memory")

MEMORY_PROMPT_LIMIT = 40
ENTRY_TYPES = ("fact", "decision", "preference")

_DISTILL_SYSTEM = """You extract durable project memory from a single Q&A exchange.
Respond with ONLY a JSON object: {"worth_remembering": true/false, "entry_type": \
"fact"|"decision"|"preference", "content": "one sentence, third person, dense"}.
Set worth_remembering to false for exchanges that are plain lookups with no lasting \
relevance (e.g. "what page is X on"), and for answers that say the documents do not \
cover the question. Set it true for things that would matter in a later session: \
established facts about the system, decisions taken, stated preferences or constraints."""


def list_entries(knowledge_base_id, limit: int = 200) -> list[dict]:
    with connection() as conn:
        return conn.execute(
            """SELECT id, entry_type, content, source_chat_id, created_at FROM memory_entries
               WHERE knowledge_base_id=%s ORDER BY created_at DESC LIMIT %s""",
            (knowledge_base_id, limit),
        ).fetchall()


def render_block(knowledge_base_id) -> str:
    """Prompt block, oldest first so it reads chronologically."""
    if not knowledge_base_id:
        return ""
    entries = list(reversed(list_entries(knowledge_base_id, MEMORY_PROMPT_LIMIT)))
    if not entries:
        return ""
    lines = "\n".join(f"- [{entry['entry_type']}] {entry['content']}" for entry in entries)
    return f"PROJECT MEMORY (earlier findings in this knowledge base; context, not evidence - never cite it):\n{lines}\n"


def _parse(raw: str) -> dict | None:
    try:
        return json.loads(raw.strip())
    except Exception:
        match = re.search(r"\{.*\}", raw, re.S)
        if not match:
            return None
        try:
            return json.loads(match.group(0))
        except Exception:
            return None


def distill_exchange(knowledge_base_id, chat_id, question: str, answer: str) -> None:
    """Best effort: any failure is logged and dropped, never surfaced to the chat."""
    try:
        parsed = _parse(llm.chat(_DISTILL_SYSTEM, f"Question: {question}\n\nAnswer: {answer}", temperature=0.0))
        if not isinstance(parsed, dict) or not parsed.get("worth_remembering"):
            return
        content = str(parsed.get("content") or "").strip()
        if not content:
            return
        entry_type = parsed.get("entry_type") if parsed.get("entry_type") in ENTRY_TYPES else "fact"
        with connection() as conn:
            # a reference library is shared by every account, so one user's
            # conversation must never write into it
            library = conn.execute("SELECT is_reference FROM knowledge_bases WHERE id=%s", (knowledge_base_id,)).fetchone()
            if not library or library["is_reference"]:
                return
            conn.execute(
                """INSERT INTO memory_entries(knowledge_base_id, entry_type, content, source_chat_id)
                   VALUES(%s, %s, %s, %s)""",
                (knowledge_base_id, entry_type, content[:1000], chat_id),
            )
            conn.commit()
    except Exception:
        logger.exception("Memory distillation failed")


def distill_in_background(knowledge_base_id, chat_id, question: str, answer: str) -> None:
    """Runs after the answer has streamed, so the extra model call never delays it."""
    if not settings.memory_enabled or not knowledge_base_id:
        return
    threading.Thread(
        target=distill_exchange, args=(knowledge_base_id, chat_id, question, answer), daemon=True
    ).start()
