"""
Files on disk that belong to a document: the uploaded original and any figure
images extracted from it. Database rows cascade on their own; these don't, so
every path that deletes a document (or the chat / knowledge base holding it)
must call remove_document_files.
"""
import shutil
from pathlib import Path

from app.config import settings


def figure_dir(document_id) -> Path:
    return Path(settings.upload_dir) / "figures" / str(document_id)


def remove_document_files(document: dict) -> None:
    Path(document["storage_path"]).unlink(missing_ok=True)
    shutil.rmtree(figure_dir(document["id"]), ignore_errors=True)
