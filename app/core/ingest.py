"""
Ingestion pipeline: file -> parsed units -> chunks -> embeddings -> Chroma.
Single entry point so API routes stay thin.
"""
import uuid
from pathlib import Path
from app.parsers.pdf_parser import parse_pdf
from app.parsers.docx_parser import parse_docx
from app.core.chunking import chunk_document
from app.core.llm_client import ollama
from app.core.vectorstore import add_chunks
from app.core.structured_facts import ingest_structured_facts
from app.core.figures import extract_figures_from_pdf, extract_figures_from_docx
from app.config import settings


async def ingest_document(user_id: str, project_id: str, file_path: str, original_filename: str) -> dict:
    ext = Path(file_path).suffix.lower()
    if ext == ".pdf":
        units = parse_pdf(file_path)
        unit_key = "page"
    elif ext == ".docx":
        units = parse_docx(file_path)
        unit_key = "section"
    else:
        raise ValueError(f"Unsupported file type: {ext}")

    if not units:
        raise ValueError("No extractable text found in document")

    chunks = chunk_document(units, settings.chunk_size_tokens, settings.chunk_overlap_tokens, unit_key)
    doc_id = str(uuid.uuid4())

    texts = [c["text"] for c in chunks]
    embeddings = await ollama.embed_batch(texts)

    for c in chunks:
        c["source_file"] = original_filename

    add_chunks(user_id, project_id, doc_id, chunks, embeddings)

    # structured facts (tables -> exact-lookup key/value pairs)
    fact_count = ingest_structured_facts(user_id, project_id, doc_id, original_filename, file_path, ext)

    # existing figures/diagrams already in the document
    if ext == ".pdf":
        figure_count = extract_figures_from_pdf(user_id, project_id, doc_id, original_filename, file_path)
    else:
        figure_count = extract_figures_from_docx(user_id, project_id, doc_id, original_filename, file_path)

    return {
        "doc_id": doc_id,
        "filename": original_filename,
        "chunk_count": len(chunks),
        "unit_type": unit_key,
        "unit_count": len(units),
        "structured_fact_count": fact_count,
        "figure_count": figure_count,
    }
