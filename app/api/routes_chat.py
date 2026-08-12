import httpx
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pathlib import Path
from app.core.query_pipeline import answer_question, answer_question_stream
from app.core.diagram import generate_diagram
from app.core.figures import find_matching_figure, FIGURE_DIR
from app.core.hybrid_search import hybrid_search
from app.core.llm_client import ollama
from app.models.schemas import QuestionRequest, AnswerResponse, DiagramRequest, DiagramResponse
from app.config import settings

router = APIRouter(tags=["chat"])


@router.post("/ask", response_model=AnswerResponse)
async def ask(req: QuestionRequest):
    result = await answer_question(req.user_id, req.project_id, req.question)
    return AnswerResponse(**result)


async def _stream_with_error_reporting(user_id: str, project_id: str, question: str):
    """
    A streaming response has already sent its 200 headers by the time the model
    backend can fail, so the app-level httpx handler can't turn that into a 503.
    Emit the failure into the stream instead of dropping the connection silently.
    """
    try:
        async for token in answer_question_stream(user_id, project_id, question):
            yield token
    except httpx.HTTPError as exc:
        yield (f"\n\n[error] Model backend ({settings.ollama_host}) did not respond: "
               f"{type(exc).__name__}. Check that Ollama is running.")


@router.post("/ask/stream")
async def ask_stream(req: QuestionRequest):
    return StreamingResponse(
        _stream_with_error_reporting(req.user_id, req.project_id, req.question),
        media_type="text/plain",
    )


@router.post("/diagram", response_model=DiagramResponse)
async def diagram(req: DiagramRequest):
    # prefer a figure that already exists in the source documents
    existing = find_matching_figure(req.user_id, req.project_id, req.request)
    if existing:
        rel_path = Path(existing["image_path"]).relative_to(FIGURE_DIR)
        return DiagramResponse(
            mermaid="",
            existing_figure_path=f"/figures/{rel_path.as_posix()}",
            existing_figure_caption=existing["caption"],
            source=f"{existing['source_file']} ({existing['locator']})",
        )

    q_embedding = await ollama.embed(req.request)
    candidates = hybrid_search(req.user_id, req.project_id, req.request, q_embedding, settings.top_k_retrieval)
    context = "\n\n".join(c["text"] for c in candidates[:6])
    mermaid = await generate_diagram(context, req.request)
    return DiagramResponse(mermaid=mermaid, source="generated")
