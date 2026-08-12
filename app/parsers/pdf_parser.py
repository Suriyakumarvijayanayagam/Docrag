"""
PDF text extraction. Returns page-level text with page numbers preserved,
so citations later can say "page 4" instead of just "somewhere in the doc".
"""
import fitz  # PyMuPDF


def parse_pdf(file_path: str) -> list[dict]:
    """
    Returns: [{"page": 1, "text": "..."}, {"page": 2, "text": "..."}, ...]
    Skips empty pages.
    """
    pages = []
    with fitz.open(file_path) as doc:
        for i, page in enumerate(doc):
            text = page.get_text("text").strip()
            if text:
                pages.append({"page": i + 1, "text": text})
    return pages
