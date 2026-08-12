from fastapi import APIRouter
from app.core.vectorstore import project_doc_count
from app.core.memory import get_project_memory
from app.models.schemas import ProjectStatus

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("/status", response_model=ProjectStatus)
async def status(user_id: str, project_id: str):
    doc_count = project_doc_count(user_id, project_id)
    mem = get_project_memory(user_id, project_id, limit=1000)
    return ProjectStatus(
        user_id=user_id,
        project_id=project_id,
        document_count=doc_count,
        memory_entry_count=len(mem),
    )


@router.get("/memory")
async def memory(user_id: str, project_id: str):
    return {"entries": get_project_memory(user_id, project_id)}
