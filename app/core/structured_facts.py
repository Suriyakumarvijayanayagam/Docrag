"""
Tables in technical docs (spec sheets, pinouts, parameter tables) are where
exact answers live. Chunk-and-embed treats a table row as fuzzy text, which
is exactly wrong for "what's the max operating temp" - that needs an exact
lookup, not a semantic guess.

This module extracts tables at ingest time into a separate SQLite table of
(label, value) pairs, scoped per user/project/doc, queryable by substring
match before falling back to RAG.
"""
import sqlite3
import time
from contextlib import contextmanager
from docx import Document
from app.config import settings
from app.core.text_match import content_tokens

_SCHEMA = """
CREATE TABLE IF NOT EXISTS structured_facts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    doc_id TEXT NOT NULL,
    source_file TEXT,
    locator TEXT,
    label TEXT NOT NULL,
    value TEXT NOT NULL,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_facts_scope ON structured_facts(user_id, project_id);
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


def init_facts_db():
    with _conn() as c:
        c.executescript(_SCHEMA)


def _store_facts(user_id: str, project_id: str, doc_id: str, source_file: str, facts: list[tuple[str, str, str]]):
    """facts: list of (locator, label, value)"""
    if not facts:
        return
    with _conn() as c:
        c.executemany(
            "INSERT INTO structured_facts (user_id, project_id, doc_id, source_file, locator, label, value, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [(user_id, project_id, doc_id, source_file, loc, label, value, time.time()) for loc, label, value in facts],
        )


def extract_facts_from_docx_tables(file_path: str) -> list[tuple[str, str, str]]:
    """
    Heuristic: 2-column tables are treated as label/value pairs.
    Wider tables use the header row as labels for each subsequent row,
    flattened to "RowEntity.ColumnHeader -> cell value".
    """
    doc = Document(file_path)
    facts = []
    for t_idx, table in enumerate(doc.tables):
        rows = [[c.text.strip() for c in row.cells] for row in table.rows]
        rows = [r for r in rows if any(r)]
        if not rows:
            continue

        if all(len(r) == 2 for r in rows):
            for r_idx, (label, value) in enumerate(rows):
                if label and value:
                    facts.append((f"table {t_idx+1} row {r_idx+1}", label, value))
        elif len(rows) > 1:
            header = rows[0]
            for r_idx, row in enumerate(rows[1:], start=1):
                row_entity = row[0] if row else f"row {r_idx}"
                for col_idx, cell_val in enumerate(row[1:], start=1):
                    if col_idx < len(header) and cell_val:
                        label = f"{row_entity}.{header[col_idx]}"
                        facts.append((f"table {t_idx+1} row {r_idx+1}", label, cell_val))
    return facts


def extract_facts_from_pdf_tables(file_path: str) -> list[tuple[str, str, str]]:
    """Uses PyMuPDF's built-in table finder."""
    import fitz
    facts = []
    with fitz.open(file_path) as doc:
        for page_idx, page in enumerate(doc):
            try:
                found = page.find_tables()
            except Exception:
                continue
            for t_idx, table in enumerate(found.tables):
                rows = table.extract()
                rows = [[str(c).strip() if c else "" for c in r] for r in rows]
                rows = [r for r in rows if any(r)]
                if not rows:
                    continue
                if all(len(r) == 2 for r in rows):
                    for r_idx, (label, value) in enumerate(rows):
                        if label and value:
                            facts.append((f"page {page_idx+1} table {t_idx+1} row {r_idx+1}", label, value))
                elif len(rows) > 1:
                    header = rows[0]
                    for r_idx, row in enumerate(rows[1:], start=1):
                        row_entity = row[0] if row else f"row {r_idx}"
                        for col_idx, cell_val in enumerate(row[1:], start=1):
                            if col_idx < len(header) and cell_val:
                                label = f"{row_entity}.{header[col_idx]}"
                                facts.append((f"page {page_idx+1} table {t_idx+1} row {r_idx+1}", label, cell_val))
    return facts


def ingest_structured_facts(user_id: str, project_id: str, doc_id: str, source_file: str, file_path: str, ext: str):
    if ext == ".docx":
        facts = extract_facts_from_docx_tables(file_path)
    elif ext == ".pdf":
        facts = extract_facts_from_pdf_tables(file_path)
    else:
        facts = []
    _store_facts(user_id, project_id, doc_id, source_file, facts)
    return len(facts)


def delete_doc_facts(user_id: str, project_id: str, doc_id: str) -> int:
    """Facts live outside the vector store, so deleting a document has to
    remove them explicitly - otherwise its spec values keep answering
    questions after the document itself is gone."""
    with _conn() as c:
        cur = c.execute(
            "DELETE FROM structured_facts WHERE user_id = ? AND project_id = ? AND doc_id = ?",
            (user_id, project_id, doc_id),
        )
        return cur.rowcount


def fact_counts_by_doc(user_id: str, project_id: str) -> dict:
    """{doc_id: number of extracted facts} for this tenant."""
    with _conn() as c:
        rows = c.execute(
            "SELECT doc_id, COUNT(*) AS n FROM structured_facts "
            "WHERE user_id = ? AND project_id = ? GROUP BY doc_id",
            (user_id, project_id),
        ).fetchall()
    return {r["doc_id"]: r["n"] for r in rows}


def lookup_facts(user_id: str, project_id: str, question: str, limit: int = 8) -> list[dict]:
    """
    Whole-word overlap lookup: pulls facts whose label shares a meaningful
    token with the question. Not a replacement for RAG, a fast-path in front
    of it for exact spec questions.

    These facts are presented to the user as "exact_match" sources, so a
    false positive is expensive - it puts an unrelated spec row in front of
    a reviewer with an authoritative label, and puts it in the prompt where
    it can steer the answer. Hence whole-word, stopword-free matching and
    ranking by overlap strength rather than "any token matched".
    """
    tokens = content_tokens(question)
    if not tokens:
        return []
    with _conn() as c:
        rows = c.execute(
            "SELECT source_file, locator, label, value FROM structured_facts WHERE user_id = ? AND project_id = ?",
            (user_id, project_id),
        ).fetchall()

    scored = []
    for r in rows:
        overlap = len(tokens & content_tokens(r["label"]))
        if overlap:
            scored.append((overlap, dict(r)))

    # strongest label overlap first, so `limit` truncates the weakest matches
    scored.sort(key=lambda pair: pair[0], reverse=True)
    best = scored[0][0] if scored else 0
    # a question that matches one label on 2 words and another on 1 is asking
    # about the first; keep only the top overlap tier
    return [r for score, r in scored if score == best][:limit]
