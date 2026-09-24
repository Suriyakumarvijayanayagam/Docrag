"""Validating uploaded files before they are stored and queued for indexing."""
from pathlib import Path
from uuid import UUID

from fastapi import HTTPException, UploadFile

from app.config import settings
from app.ingestion import SUPPORTED_EXTENSIONS
from app.storage import store_document

DOCUMENT_COLUMNS = (
    "id", "filename", "content_type", "byte_size", "status", "error_message",
    "page_count", "chunk_count", "fact_count", "figure_count", "created_at", "updated_at",
)


def document_row(row: dict) -> dict:
    return {key: row[key] for key in DOCUMENT_COLUMNS}


def save_uploads(files: list[UploadFile], user_id: UUID, kb_id: UUID | None = None, chat_id: UUID | None = None) -> list[dict]:
    if not files:
        raise HTTPException(status_code=400, detail="Choose at least one file")
    saved = []
    for upload in files:
        original_name = Path(upload.filename or "document").name
        extension = Path(original_name).suffix.lower()
        if extension not in SUPPORTED_EXTENSIONS:
            raise HTTPException(status_code=415, detail=f"Unsupported file type: {extension or 'unknown'}")
        content = upload.file.read(settings.max_upload_mb * 1024 * 1024 + 1)
        if not content:
            raise HTTPException(status_code=400, detail=f"{original_name} is empty")
        if len(content) > settings.max_upload_mb * 1024 * 1024:
            raise HTTPException(status_code=413, detail=f"{original_name} exceeds {settings.max_upload_mb} MB")
        row = store_document(content, original_name, upload.content_type, kb_id=kb_id, chat_id=chat_id, user_id=user_id)
        saved.append(row if row.get("status") == "duplicate" else document_row(row))
    return saved


