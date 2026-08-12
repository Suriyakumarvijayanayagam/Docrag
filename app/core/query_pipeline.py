"""
Full answer flow, upgraded:
  1. fast-path: exact structured-fact lookup (spec/table questions answered directly)
  2. embed question
  3. hybrid retrieval (vector + BM25, fused) - scoped to user+project
  4. detect cross-document comparison intent -> ensure retrieval spans multiple source docs
  5. rerank, compute a confidence label from the score distribution
  6. LLM answers with grounded facts vs insight kept visibly separate
  7. curated write to persistent project memory
"""
from app.core.llm_client import ollama
from app.core.hybrid_search import hybrid_search
from app.core.reranker import rerank
from app.core.memory import render_memory_block, add_entry
from app.core.structured_facts import lookup_facts
from app.core.memory_distill import distill_exchange
from app.config import settings

_ANSWER_SYSTEM = """You are a technical document assistant. You answer using two clearly \
separated parts:

1. FROM THE DOCUMENTS: only what is directly supported by the provided passages/facts. \
Cite the source locator (page/section) given with each passage. If the documents \
don't cover something, say so plainly - do not fill the gap silently. If passages come \
from multiple different source files, synthesize across them explicitly when the \
question calls for comparison.

2. ADDITIONAL INSIGHT: your own technical analysis, context, or implications that \
go beyond what's written - clearly labeled as your own addition, not document content.

Never blend the two into one undifferentiated paragraph. Use the project context \
provided to stay consistent with earlier decisions in this project, but do not \
restate it back to the user unless it's directly relevant to this question."""

# Long enough to cover a retrieved chunk, short enough to keep the response
# small when several sources come back.
SNIPPET_CHARS = 2000

_COMPARISON_KEYWORDS = ("compare", "vs", "versus", "difference between", "which is better", "across")


def _is_comparison_query(question: str) -> bool:
    q = question.lower()
    return any(k in q for k in _COMPARISON_KEYWORDS)


def _ensure_doc_diversity(chunks: list[dict], min_docs: int = 2) -> list[dict]:
    """
    For comparison-style questions, a naive top-k can end up all from one
    document if it happens to score highest. This re-balances the result
    set so multiple source documents are represented when they exist.
    """
    by_doc: dict[str, list[dict]] = {}
    for c in chunks:
        key = c["metadata"].get("doc_id", "unknown")
        by_doc.setdefault(key, []).append(c)

    if len(by_doc) < min_docs:
        return chunks  # only one doc available, nothing to diversify

    result, doc_iters = [], {k: iter(v) for k, v in by_doc.items()}
    while len(result) < len(chunks):
        progressed = False
        for k, it in doc_iters.items():
            item = next(it, None)
            if item:
                result.append(item)
                progressed = True
        if not progressed:
            break
    return result


def _confidence_label(top_chunks: list[dict], fact_matches: list = ()) -> str:
    """
    Confidence in the *grounding*, on the reranker's 0-10 scale: high >=7,
    medium >=4, else low.

    Keyed off the best passage, not the mean of top_k. An answer is grounded
    if one retrieved passage genuinely supports it; the other four are padding
    for context. Averaging over them meant a question answered perfectly from
    a 10-scoring passage still reported "low" because the filler scored 0 -
    the meter contradicted the answer sitting next to it.
    """
    if not top_chunks and not fact_matches:
        return "none"

    best = max((c.get("rerank_score", 0) for c in top_chunks), default=0)

    # An exact table lookup is grounding by construction - it is a value read
    # out of the document, not a semantic guess - so it floors the label at
    # medium even when the surrounding prose retrieves poorly.
    if fact_matches:
        best = max(best, 4)

    if best >= 7:
        return "high"
    elif best >= 4:
        return "medium"
    return "low"


async def answer_question(user_id: str, project_id: str, question: str) -> dict:
    fact_matches = lookup_facts(user_id, project_id, question)

    q_embedding = await ollama.embed(question)
    candidates = hybrid_search(user_id, project_id, question, q_embedding, settings.top_k_retrieval)

    if not candidates and not fact_matches:
        return {
            "answer": "No documents have been ingested for this project yet, so I have nothing to ground an answer in.",
            "sources": [],
            "confidence": "none",
        }

    if _is_comparison_query(question):
        candidates = _ensure_doc_diversity(candidates)

    top_chunks = await rerank(question, candidates, settings.top_k_after_rerank) if candidates else []
    confidence = _confidence_label(top_chunks, fact_matches)

    facts_block = ""
    if fact_matches:
        facts_block = "Exact specification lookups:\n" + "\n".join(
            f"- {f['label']}: {f['value']} (source: {f['source_file']}, {f['locator']})" for f in fact_matches
        )

    passages_block = "\n\n".join(
        f"[Source: {c['metadata'].get('source_file', 'unknown')}, "
        f"{'page ' + str(c['metadata']['page']) if 'page' in c['metadata'] else 'section ' + str(c['metadata'].get('section'))}]\n"
        f"{c['text']}"
        for c in top_chunks
    )

    memory_block = render_memory_block(user_id, project_id)

    user_prompt = f"{memory_block}\n\n{facts_block}\n\nRetrieved passages:\n{passages_block}\n\nQuestion: {question}"

    answer = await ollama.chat(_ANSWER_SYSTEM, user_prompt)

    await distill_exchange(user_id, project_id, question, answer)

    sources = [
        {
            "file": c["metadata"].get("source_file"),
            "locator": c["metadata"].get("page") or c["metadata"].get("section"),
            "relevance": round(c.get("rerank_score", c.get("score", 0)), 2),
            # the passage itself, so a client can show the reader exactly which
            # text on that page the answer was drawn from rather than just
            # pointing at the page and asking them to find it
            "snippet": c["text"][:SNIPPET_CHARS],
        }
        for c in top_chunks
    ]
    for f in fact_matches:
        sources.append({"file": f["source_file"], "locator": f["locator"], "relevance": "exact_match"})

    return {"answer": answer, "sources": sources, "confidence": confidence}


async def answer_question_stream(user_id: str, project_id: str, question: str):
    """
    Same retrieval pipeline as answer_question, but yields tokens as they
    arrive from the LLM instead of blocking for the full response.
    Sources/confidence are yielded first as a single JSON line, then tokens.
    """
    import json

    fact_matches = lookup_facts(user_id, project_id, question)
    q_embedding = await ollama.embed(question)
    candidates = hybrid_search(user_id, project_id, question, q_embedding, settings.top_k_retrieval)

    if not candidates and not fact_matches:
        yield json.dumps({"type": "meta", "sources": [], "confidence": "none"}) + "\n"
        yield "No documents have been ingested for this project yet."
        return

    if _is_comparison_query(question):
        candidates = _ensure_doc_diversity(candidates)

    top_chunks = await rerank(question, candidates, settings.top_k_after_rerank) if candidates else []
    confidence = _confidence_label(top_chunks, fact_matches)

    sources = [
        {
            "file": c["metadata"].get("source_file"),
            "locator": c["metadata"].get("page") or c["metadata"].get("section"),
            "relevance": round(c.get("rerank_score", c.get("score", 0)), 2),
            # the passage itself, so a client can show the reader exactly which
            # text on that page the answer was drawn from rather than just
            # pointing at the page and asking them to find it
            "snippet": c["text"][:SNIPPET_CHARS],
        }
        for c in top_chunks
    ]
    yield json.dumps({"type": "meta", "sources": sources, "confidence": confidence}) + "\n"

    facts_block = ""
    if fact_matches:
        facts_block = "Exact specification lookups:\n" + "\n".join(
            f"- {f['label']}: {f['value']} (source: {f['source_file']}, {f['locator']})" for f in fact_matches
        )
    passages_block = "\n\n".join(
        f"[Source: {c['metadata'].get('source_file', 'unknown')}, "
        f"{'page ' + str(c['metadata']['page']) if 'page' in c['metadata'] else 'section ' + str(c['metadata'].get('section'))}]\n"
        f"{c['text']}"
        for c in top_chunks
    )
    memory_block = render_memory_block(user_id, project_id)
    user_prompt = f"{memory_block}\n\n{facts_block}\n\nRetrieved passages:\n{passages_block}\n\nQuestion: {question}"

    full_answer = ""
    async for token in ollama.chat_stream(_ANSWER_SYSTEM, user_prompt):
        full_answer += token
        yield token

    await distill_exchange(user_id, project_id, question, full_answer)
