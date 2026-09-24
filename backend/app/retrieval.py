"""
Hybrid retrieval: pgvector cosine search + PostgreSQL full-text search, fused
with weighted Reciprocal Rank Fusion. Full-text catches exact tokens (part
numbers, register names) that embeddings drift away from; vectors catch
paraphrases.

Every query here is limited to what one chat may see: ready documents in its
knowledge base plus files attached to the chat itself (SCOPE_SQL). Access to
the knowledge base is checked by the API layer before retrieval is called.
"""
from collections import defaultdict
import re
from uuid import UUID

from pgvector import Vector

from app import llm
from app.config import settings
from app.db import connection
from app.facts import match_facts

RRF_K = 60
VECTOR_WEIGHT = 0.7
LEXICAL_WEIGHT = 0.3
# Highest possible fused score: rank 1 in both lists. Bounds the scale the
# reranker's retrieval-only fallback maps from.
MAX_RRF = (VECTOR_WEIGHT + LEXICAL_WEIGHT) / (RRF_K + 1)

MAX_EXHAUSTIVE_CHUNKS = 24
ROW_RE = re.compile(r"(?m)^(?:Sheet (.*?) — )?Row (\d+) — (.*)$")
QUERY_STOP_WORDS = {
    "a", "all", "an", "and", "are", "do", "each", "every", "for", "from", "give",
    "how", "in", "list", "many", "me", "of", "please", "show", "the", "to", "what",
    "which", "who", "with",
}
SUMMARY_ROW_VALUES = {"total", "grand total", "subtotal", "sub total", "overall total", "sum"}

SCOPE_SQL = """d.status='ready'
   AND ((%(kb)s::uuid IS NOT NULL AND d.knowledge_base_id=%(kb)s::uuid)
        OR d.conversation_id=%(chat)s::uuid)"""

_COMPARISON_RE = re.compile(r"\b(compare|comparison|vs\.?|versus|difference between|differences|which is better|across)\b")


def _scope(knowledge_base_id: str | None, chat_id: str) -> dict:
    return {"kb": UUID(knowledge_base_id) if knowledge_base_id else None, "chat": UUID(chat_id)}


def is_exhaustive_query(query: str) -> bool:
    normalized = query.lower()
    if re.search(r"\b(how many|count|number of|total number|total count)\b", normalized):
        return True
    return bool(re.search(r"\b(list|enumerate)\b", normalized)) or bool(
        re.search(r"\b(all|every|each)\b", normalized)
        and re.search(r"\b(names?|records?|rows?|entries|items|people|members|parts?|students?)\b", normalized)
    )


def is_comparison_query(query: str) -> bool:
    return bool(_COMPARISON_RE.search(query.lower()))


def ensure_document_diversity(candidates: list[dict], min_documents: int = 2) -> list[dict]:
    """
    A comparison question can retrieve only from whichever document scored
    highest. Interleave by document so each one reaches the reranker.
    """
    by_document: dict[str, list[dict]] = defaultdict(list)
    for candidate in candidates:
        by_document[str(candidate["document_id"])].append(candidate)
    if len(by_document) < min_documents:
        return candidates
    queues = [list(items) for items in by_document.values()]
    result = []
    while any(queues):
        for queue in queues:
            if queue:
                result.append(queue.pop(0))
    return result


def _label_column(headers: list[str]) -> str | None:
    """The column that names each record: the first header mentioning a name, else the first column."""
    for header in headers:
        if "name" in header.lower():
            return header
    return headers[0] if headers else None


def spreadsheet_facts(sources: list[dict]) -> list[str]:
    """
    Counts records from complete spreadsheet evidence, never from chunk labels
    or the largest row number (title and header rows make those wrong).
    """
    rows_by_document: dict[str, dict[tuple[str, int], dict[str, str]]] = defaultdict(dict)
    names_by_document: dict[str, str] = {}
    complete_documents: set[str] = set()

    for source in sources:
        if not source.get("filename", "").lower().endswith((".xlsx", ".xlsm")):
            continue
        document_id = str(source["document_id"])
        names_by_document[document_id] = source["filename"]
        if source.get("document_complete"):
            complete_documents.add(document_id)
        fallback_sheet = source.get("section") or ""
        for match in ROW_RE.finditer(source.get("content", "")):
            sheet, row_number, payload = match.groups()
            fields: dict[str, str] = {}
            for cell in payload.split(" | "):
                if ": " in cell:
                    header, value = cell.split(": ", 1)
                    fields[header.strip()] = value.strip()
            # keyed by physical row, so a row repeated across chunks counts once
            rows_by_document[document_id][(sheet or fallback_sheet, int(row_number))] = fields

    facts = []
    for document_id in sorted(complete_documents):
        rows = [
            row for row in rows_by_document.get(document_id, {}).values()
            if not any(value.strip().lower() in SUMMARY_ROW_VALUES for value in row.values())
        ]
        if not rows:
            continue
        label = _label_column(list(dict.fromkeys(header for row in rows for header in row)))
        labels = [row.get(label, "").strip() for row in rows] if label else []
        labels = [value for value in labels if value]
        fact = f"{names_by_document[document_id]}: {len(rows)} data rows, excluding title, header and total rows."
        if labels:
            fact += f" Non-empty '{label}' values in sheet order ({len(labels)}): {'; '.join(labels)}"
        facts.append(fact)
    return facts


def _filename_terms(filename: str) -> set[str]:
    terms = set(re.findall(r"[a-z0-9]+", filename.lower()))
    return {term[:-1] if len(term) > 4 and term.endswith("s") else term for term in terms}


def _query_terms(query: str) -> set[str]:
    terms = set(re.findall(r"[a-z0-9]+", query.lower())) - QUERY_STOP_WORDS
    return {term[:-1] if len(term) > 4 and term.endswith("s") else term for term in terms}


def retrieve(query: str, knowledge_base_id: str | None, chat_id: str, limit: int) -> list[dict]:
    """
    Fused candidates, best first. For count/list questions the single most
    relevant document is returned whole instead (up to MAX_EXHAUSTIVE_CHUNKS),
    with document_complete saying whether it fit.
    """
    exhaustive = is_exhaustive_query(query)
    query_terms = _query_terms(query) or set(re.findall(r"[a-z0-9]+", query.lower()))
    lexical_query = " | ".join(sorted(query_terms)[:16])
    query_vector = llm.embed_query(query)
    scope = _scope(knowledge_base_id, chat_id)
    ranked: dict[int, dict] = {}
    with connection() as conn:
        if query_vector:
            vector_rows = conn.execute(
                f"""SELECT c.id, c.content, c.page_start, c.page_end, c.section, c.token_count,
                          d.id AS document_id, d.filename,
                          1 - (c.embedding <=> %(vec)s) AS similarity
                   FROM chunks c JOIN documents d ON d.id=c.document_id
                   WHERE {SCOPE_SQL}
                   ORDER BY c.embedding <=> %(vec)s LIMIT 40""",
                {**scope, "vec": Vector(query_vector)},
            ).fetchall()
            for rank, row in enumerate(vector_rows, start=1):
                if float(row["similarity"] or 0) < settings.retrieval_min_similarity:
                    continue
                ranked[row["id"]] = {**row, "rrf": VECTOR_WEIGHT / (RRF_K + rank)}

        if lexical_query:
            lexical_rows = conn.execute(
                f"""SELECT c.id, c.content, c.page_start, c.page_end, c.section, c.token_count,
                          d.id AS document_id, d.filename,
                          ts_rank_cd(c.search_vector, to_tsquery('simple', %(q)s)) AS lexical_score
                   FROM chunks c JOIN documents d ON d.id=c.document_id
                   WHERE {SCOPE_SQL} AND c.search_vector @@ to_tsquery('simple', %(q)s)
                   ORDER BY lexical_score DESC LIMIT 40""",
                {**scope, "q": lexical_query},
            ).fetchall()
            for rank, row in enumerate(lexical_rows, start=1):
                if row["id"] in ranked:
                    ranked[row["id"]]["rrf"] += LEXICAL_WEIGHT / (RRF_K + rank)
                else:
                    ranked[row["id"]] = {**row, "rrf": LEXICAL_WEIGHT / (RRF_K + rank)}

        results = sorted(ranked.values(), key=lambda row: row["rrf"], reverse=True)
        if not exhaustive:
            return results[:limit]

        selected_document_id = None
        if results:
            document_scores: dict[str, list[float]] = defaultdict(list)
            for row in results:
                document_scores[str(row["document_id"])].append(float(row["rrf"]))
            selected_document_id = max(
                document_scores,
                key=lambda document_id: sum(sorted(document_scores[document_id], reverse=True)[:3]),
            )
        # A filename match identifies a workbook even when its rows don't repeat the query terms.
        documents = conn.execute(f"SELECT d.id, d.filename FROM documents d WHERE {SCOPE_SQL}", scope).fetchall()
        filename_matches = [(len(query_terms & _filename_terms(document["filename"])), document) for document in documents]
        if filename_matches:
            match_count, best_match = max(filename_matches, key=lambda item: item[0])
            if match_count:
                selected_document_id = str(best_match["id"])
        if not selected_document_id:
            return []

        complete_rows = conn.execute(
            f"""SELECT c.id, c.content, c.page_start, c.page_end, c.section, c.token_count,
                      d.id AS document_id, d.filename, count(*) OVER() AS document_chunk_count
               FROM chunks c JOIN documents d ON d.id=c.document_id
               WHERE d.id=%(doc)s AND {SCOPE_SQL}
               ORDER BY c.chunk_index LIMIT %(limit)s""",
            {**scope, "doc": UUID(selected_document_id), "limit": MAX_EXHAUSTIVE_CHUNKS},
        ).fetchall()
    total_chunks = int(complete_rows[0]["document_chunk_count"]) if complete_rows else 0
    document_complete = 0 < total_chunks <= MAX_EXHAUSTIVE_CHUNKS
    return [
        {**row, "rrf": 1 / (RRF_K + rank), "document_complete": document_complete, "document_chunk_count": total_chunks}
        for rank, row in enumerate(complete_rows, start=1)
    ]


def lookup_facts(query: str, knowledge_base_id: str | None, chat_id: str) -> list[dict]:
    with connection() as conn:
        facts = conn.execute(
            f"""SELECT f.id, f.page, f.locator, f.label, f.value, d.id AS document_id, d.filename
               FROM structured_facts f JOIN documents d ON d.id=f.document_id
               WHERE {SCOPE_SQL}""",
            _scope(knowledge_base_id, chat_id),
        ).fetchall()
    return match_facts(query, facts)


def figures_in_scope(knowledge_base_id: str | None, chat_id: str) -> list[dict]:
    with connection() as conn:
        return conn.execute(
            f"""SELECT f.id, f.page, f.locator, f.caption, d.id AS document_id, d.filename
               FROM figures f JOIN documents d ON d.id=f.document_id
               WHERE {SCOPE_SQL} ORDER BY d.created_at, f.id""",
            _scope(knowledge_base_id, chat_id),
        ).fetchall()


def history_for_chat(chat_id: str, before_message_id: str, limit: int = 8) -> list[dict]:
    with connection() as conn:
        rows = conn.execute(
            """SELECT role, content FROM messages
               WHERE chat_id=%s AND id<>%s AND diagram IS NULL ORDER BY created_at DESC LIMIT %s""",
            (UUID(chat_id), UUID(before_message_id), limit),
        ).fetchall()
    return [{"role": row["role"], "content": row["content"]} for row in reversed(rows)]
