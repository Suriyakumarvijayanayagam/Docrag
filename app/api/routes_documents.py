import shutil
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse
from app.core.ingest import ingest_document
from app.core.vectorstore import delete_document, list_documents, project_doc_count
from app.core.structured_facts import delete_doc_facts, fact_counts_by_doc
from app.core.figures import delete_doc_figures, figure_counts_by_doc
from app.models.schemas import DocumentSummary, IngestResponse
from app.config import settings

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("/upload", response_model=IngestResponse)
async def upload_document(
    user_id: str = Form(...),
    project_id: str = Form(...),
    file: UploadFile = File(...),
):
    ext = Path(file.filename).suffix.lower()
    if ext not in (".pdf", ".docx"):
        raise HTTPException(400, "Only .pdf and .docx files are supported")

    upload_dir = Path(settings.upload_dir) / user_id / project_id
    upload_dir.mkdir(parents=True, exist_ok=True)
    dest = upload_dir / file.filename

    with dest.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    try:
        result = await ingest_document(user_id, project_id, str(dest), file.filename)
    except ValueError as e:
        raise HTTPException(422, str(e))

    return IngestResponse(**result)


@router.delete("/{doc_id}")
async def remove_document(doc_id: str, user_id: str, project_id: str):
    # a document lives in three places - chunks in Chroma, facts and figures in
    # SQLite - and all three are scoped by (user_id, project_id, doc_id)
    delete_document(user_id, project_id, doc_id)
    facts_removed = delete_doc_facts(user_id, project_id, doc_id)
    figures_removed = delete_doc_figures(user_id, project_id, doc_id)
    return {
        "status": "deleted",
        "doc_id": doc_id,
        "facts_removed": facts_removed,
        "figures_removed": figures_removed,
    }


@router.get("/count")
async def doc_count(user_id: str, project_id: str):
    return {"count": project_doc_count(user_id, project_id)}


@router.get("/{doc_id}/file")
async def doc_file(doc_id: str, user_id: str, project_id: str):
    """
    Serves the original uploaded file so the console can show the actual
    document next to the answer, and open it at a cited page.

    The filename is looked up from this tenant's own store rather than taken
    from the request, so a doc_id belonging to another tenant simply isn't
    found - and a crafted filename can't escape the upload directory.
    """
    match = next(
        (d for d in list_documents(user_id, project_id) if d["doc_id"] == doc_id),
        None,
    )
    if not match:
        raise HTTPException(404, "No such document in this project")

    path = (Path(settings.upload_dir) / user_id / project_id / match["filename"]).resolve()
    root = Path(settings.upload_dir).resolve()
    if root not in path.parents or not path.is_file():
        raise HTTPException(404, "Source file is no longer on disk")

    media = "application/pdf" if path.suffix.lower() == ".pdf" else "application/octet-stream"
    return FileResponse(str(path), media_type=media, filename=match["filename"])


@router.get("/list", response_model=list[DocumentSummary])
async def doc_list(user_id: str, project_id: str):
    """
    Documents currently ingested for this tenant, with their extracted fact and
    figure counts. Lets a client rebuild its document list after a reload
    instead of only knowing about uploads it made itself.
    """
    facts = fact_counts_by_doc(user_id, project_id)
    figures = figure_counts_by_doc(user_id, project_id)
    return [
        DocumentSummary(
            doc_id=d["doc_id"],
            filename=d["filename"],
            chunk_count=d["chunk_count"],
            structured_fact_count=facts.get(d["doc_id"], 0),
            figure_count=figures.get(d["doc_id"], 0),
        )
        for d in list_documents(user_id, project_id)
    ]
