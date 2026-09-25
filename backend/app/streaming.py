"""
Server-sent event streams for a chat turn. Events, in order:
  sources  {sources, confidence}   what the answer is grounded in
  diagram  {diagram}               diagram turns only
  delta    {text}                  answer tokens
  done     {message}               the stored assistant message
  error    {message}               instead of done, on failure
"""
import json
import logging
import re

from psycopg.types.json import Jsonb

from app import calc_intent, llm, memory
from app.answer import build_sources, prepare, public_sources
from app.db import connection
from app.figures import best_figure, generate_mermaid
from app.retrieval import figures_in_scope, retrieve

logger = logging.getLogger("datum.api")

_DIAGRAM_PREFIX = re.compile(r"^\s*/?diagram\s*[:\-]?\s+", re.I)
MODEL_UNAVAILABLE = "Could not reach Ollama. Confirm it is running and the selected model is installed."


NOT_IN_DOCUMENTS = (
    "FROM THE DOCUMENTS:\nThe selected documents don't state this. The closest passages found are listed "
    "under Sources, in case the answer is worded differently there.\n\nADDITIONAL INSIGHT:\nNone."
)


def _says_nothing(answer: str) -> bool:
    """True when, without its headings and "None.", the answer has no content."""
    body = re.sub(r"(?i)from the documents:?|additional insights?:?|\bnone\b\.?|[#*_:\s]", "", answer)
    return len(body) < 5


def sse(name: str, data: dict) -> str:
    return f"event: {name}\ndata: {json.dumps(data, default=str, ensure_ascii=False)}\n\n"


def diagram_request(content: str) -> str | None:
    """'diagram: power tree' or '/diagram power tree' -> 'power tree'."""
    match = _DIAGRAM_PREFIX.match(content)
    if not match:
        return None
    return content[match.end():].strip() or None


def _scope(chat: dict) -> tuple[str | None, str, bool]:
    return (str(chat["knowledge_base_id"]) if chat["knowledge_base_id"] else None, str(chat["id"]),
            bool(chat.get("use_reference")))


def _save_assistant(chat_id, content: str, sources: list[dict], confidence: str | None, diagram: dict | None) -> dict:
    with connection() as conn:
        saved = conn.execute(
            """INSERT INTO messages(chat_id, role, content, citations, confidence, diagram)
               VALUES(%s, 'assistant', %s, %s, %s, %s) RETURNING id, created_at""",
            (chat_id, content, Jsonb(sources), confidence, Jsonb(diagram) if diagram else None),
        ).fetchone()
        conn.execute("UPDATE chats SET updated_at=now() WHERE id=%s", (chat_id,))
        conn.commit()
    return {"id": saved["id"], "role": "assistant", "content": content, "citations": sources,
            "confidence": confidence, "diagram": diagram, "created_at": saved["created_at"]}


def answer_stream(chat: dict, query: str, history: list[dict]):
    knowledge_base_id, chat_id, use_reference = _scope(chat)
    calculated = calc_intent.answer(query)
    if calculated:
        # a calculation has one right answer; the model never sees it
        yield sse("sources", {"sources": [], "confidence": None})
        yield sse("delta", {"text": calculated})
        yield sse("done", {"message": _save_assistant(chat["id"], calculated, [], None, None)})
        return
    try:
        prepared = prepare(query, knowledge_base_id, chat_id, history, use_reference)
    except Exception:
        logger.exception("Retrieval failed")
        yield sse("error", {"message": "Could not search your documents. " + MODEL_UNAVAILABLE})
        return
    sources = public_sources(prepared.sources)
    yield sse("sources", {"sources": sources, "confidence": prepared.confidence})

    parts: list[str] = []
    try:
        for text in llm.chat_stream(prepared.messages, temperature=0.0, num_ctx=prepared.num_ctx):
            parts.append(text)
            yield sse("delta", {"text": text})
    except Exception:
        logger.exception("Local model request failed")
        yield sse("error", {"message": MODEL_UNAVAILABLE})
        return
    answer = "".join(parts).strip()
    if not answer:
        answer = "I couldn't generate an answer. Check that Ollama is running and the configured chat model is installed."
        yield sse("delta", {"text": answer})
    elif _says_nothing(answer):
        # small models answer an unanswerable question with a bare "None."; say it plainly instead
        answer = NOT_IN_DOCUMENTS
    message = _save_assistant(chat["id"], answer, sources, prepared.confidence, None)
    yield sse("done", {"message": message})
    # Count/list dumps and evidence-free answers teach the project nothing durable.
    if prepared.evidence_found and not prepared.exhaustive:
        memory.distill_in_background(knowledge_base_id, chat_id, query, answer)


def diagram_stream(chat: dict, request: str):
    """An existing figure from the documents when one matches; otherwise generated Mermaid."""
    knowledge_base_id, chat_id, use_reference = _scope(chat)
    try:
        figure = best_figure(request, figures_in_scope(knowledge_base_id, chat_id, use_reference))
        if figure:
            sources: list[dict] = []
            diagram = {
                "kind": "figure", "figure_id": figure["id"], "url": f"/api/figures/{figure['id']}",
                "caption": figure["caption"], "document_id": str(figure["document_id"]), "filename": figure["filename"],
                "page": figure["page"], "source": f"{figure['filename']} ({figure['locator']})",
            }
            content = f"Found an existing figure in {figure['filename']} ({figure['locator']}): {figure['caption']}"
        else:
            candidates = retrieve(request, knowledge_base_id, chat_id, 6, use_reference)
            sources = public_sources(build_sources(candidates, []))
            mermaid = generate_mermaid("\n\n".join(candidate["content"] for candidate in candidates), request)
            diagram = {"kind": "mermaid", "mermaid": mermaid, "source": "generated"}
            content = (
                "Generated diagram. No matching figure was found in the documents, so this was drawn by the model"
                + (" from the passages below." if candidates else " without supporting passages.")
            )
    except Exception:
        logger.exception("Diagram request failed")
        yield sse("error", {"message": MODEL_UNAVAILABLE})
        return
    yield sse("sources", {"sources": sources, "confidence": None})
    yield sse("diagram", {"diagram": diagram})
    yield sse("delta", {"text": content})
    yield sse("done", {"message": _save_assistant(chat["id"], content, sources, None, diagram)})
