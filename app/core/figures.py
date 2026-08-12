"""
Technical PDFs/DOCX usually already contain the block diagrams, schematics,
and charts a person wants - regenerating them from scratch with an LLM is
strictly worse than finding and returning the real one. This module extracts
embedded images at ingest time, captions them using nearby text, and stores
them so `/diagram` can return an existing figure when one matches well
enough, falling back to LLM-generated Mermaid only when nothing fits.
"""
import sqlite3
import time
import zipfile
from pathlib import Path
from typing import Optional

from app.core.text_match import content_tokens
from contextlib import contextmanager
from app.config import settings

_SCHEMA = """
CREATE TABLE IF NOT EXISTS figures (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    doc_id TEXT NOT NULL,
    source_file TEXT,
    locator TEXT,
    caption TEXT,
    image_path TEXT NOT NULL,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_figures_scope ON figures(user_id, project_id);
"""

FIGURE_DIR = Path(settings.upload_dir).parent / "figures"


@contextmanager
def _conn():
    conn = sqlite3.connect(settings.memory_db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_figures_db():
    with _conn() as c:
        c.executescript(_SCHEMA)


def _store_figure(user_id, project_id, doc_id, source_file, locator, caption, image_path):
    with _conn() as c:
        c.execute(
            "INSERT INTO figures (user_id, project_id, doc_id, source_file, locator, caption, image_path, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (user_id, project_id, doc_id, source_file, locator, caption, image_path, time.time()),
        )


def extract_figures_from_pdf(user_id: str, project_id: str, doc_id: str, source_file: str, file_path: str) -> int:
    import fitz
    out_dir = FIGURE_DIR / user_id / project_id
    out_dir.mkdir(parents=True, exist_ok=True)

    count = 0
    with fitz.open(file_path) as doc:
        for page_idx, page in enumerate(doc):
            page_text = page.get_text("text")
            # cheap caption heuristic: first line containing "figure" or "diagram"
            caption = next(
                (line.strip() for line in page_text.splitlines()
                 if "figure" in line.lower() or "diagram" in line.lower()),
                f"Image from page {page_idx + 1}",
            )
            for img_idx, img in enumerate(page.get_images(full=True)):
                xref = img[0]
                try:
                    base = doc.extract_image(xref)
                except Exception:
                    continue
                # skip tiny images - usually logos/icons, not real diagrams
                if base["width"] < 150 or base["height"] < 150:
                    continue
                ext = base["ext"]
                fname = f"{doc_id}_p{page_idx+1}_{img_idx}.{ext}"
                fpath = out_dir / fname
                fpath.write_bytes(base["image"])
                _store_figure(user_id, project_id, doc_id, source_file, f"page {page_idx+1}", caption, str(fpath))
                count += 1
    return count


def extract_figures_from_docx(user_id: str, project_id: str, doc_id: str, source_file: str, file_path: str) -> int:
    out_dir = FIGURE_DIR / user_id / project_id
    out_dir.mkdir(parents=True, exist_ok=True)

    count = 0
    with zipfile.ZipFile(file_path) as z:
        media_files = [n for n in z.namelist() if n.startswith("word/media/")]
        for i, name in enumerate(media_files):
            data = z.read(name)
            if len(data) < 5000:  # skip tiny embedded icons
                continue
            ext = Path(name).suffix
            fname = f"{doc_id}_{i}{ext}"
            fpath = out_dir / fname
            fpath.write_bytes(data)
            _store_figure(user_id, project_id, doc_id, source_file, f"embedded image {i+1}",
                          f"Figure {i+1} from {source_file}", str(fpath))
            count += 1
    return count


# On top of the generic stopwords: "diagram"/"figure"/"schematic" appear in
# nearly every caption AND in nearly every diagram request, so counting them
# would match everything against everything.
_DIAGRAM_WORDS = frozenset({
    "diagram", "diagrams", "figure", "figures", "schematic", "schematics",
    "image", "images", "chart", "charts", "picture", "draw", "drawing",
})

# A single shared word is coincidence ("power" appears everywhere in a power
# datasheet); two independent content words is a real topical overlap.
_MIN_TOPICAL_OVERLAP = 2


def _content_tokens(text: str) -> set:
    return content_tokens(text, extra_stopwords=_DIAGRAM_WORDS)


def delete_doc_figures(user_id: str, project_id: str, doc_id: str) -> int:
    """Removes the figure rows and the extracted image files on disk, so a
    deleted document can't still be returned by /diagram."""
    with _conn() as c:
        rows = c.execute(
            "SELECT image_path FROM figures WHERE user_id = ? AND project_id = ? AND doc_id = ?",
            (user_id, project_id, doc_id),
        ).fetchall()
        c.execute(
            "DELETE FROM figures WHERE user_id = ? AND project_id = ? AND doc_id = ?",
            (user_id, project_id, doc_id),
        )
    for r in rows:
        Path(r["image_path"]).unlink(missing_ok=True)
    return len(rows)


def figure_counts_by_doc(user_id: str, project_id: str) -> dict:
    """{doc_id: number of extracted figures} for this tenant."""
    with _conn() as c:
        rows = c.execute(
            "SELECT doc_id, COUNT(*) AS n FROM figures "
            "WHERE user_id = ? AND project_id = ? GROUP BY doc_id",
            (user_id, project_id),
        ).fetchall()
    return {r["doc_id"]: r["n"] for r in rows}


def find_matching_figure(user_id: str, project_id: str, request_text: str) -> Optional[dict]:
    """
    Returns an existing figure only on genuine topical overlap with the
    request. Deliberately conservative: returning an unrelated figure is
    worse than falling back to a generated Mermaid diagram, so a weak match
    returns None and lets `/diagram` generate instead.
    """
    tokens = _content_tokens(request_text)
    if not tokens:
        return None

    with _conn() as c:
        rows = c.execute(
            "SELECT source_file, locator, caption, image_path FROM figures WHERE user_id = ? AND project_id = ?",
            (user_id, project_id),
        ).fetchall()

    best, best_score = None, 0
    for r in rows:
        # whole-word overlap, not substring - "art" must not match "part"
        score = len(tokens & _content_tokens(r["caption"]))
        if score > best_score:
            best, best_score = dict(r), score

    # a very short request ("PC-42 pinout") can only ever score 1-2, so accept
    # a full-coverage match of a short request as well
    threshold = min(_MIN_TOPICAL_OVERLAP, len(tokens))
    return best if best_score >= threshold else None
