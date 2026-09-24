import logging
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, EmailStr, Field

from app import llm, memory, welding
from app.config import settings
from app.db import connection, initialize_database
from app.retrieval import history_for_chat
from app.routes_jobs import router as jobs_router
from app.security import (
    COOKIE_NAME, User, create_token, hash_password, jwt_secret, require_kb_access, require_kb_write, verify_password,
)
from app.storage import remove_document_files
from app.uploads import DOCUMENT_COLUMNS, save_uploads
from app.streaming import answer_stream, diagram_request, diagram_stream

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("datum.api")

app = FastAPI(title="Datum", version="0.3.0", docs_url="/api/docs", openapi_url="/api/openapi.json", redoc_url=None)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type"],
)


class Credentials(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10, max_length=200)
    display_name: str = Field(min_length=1, max_length=80)


class LoginInput(BaseModel):
    email: EmailStr
    password: str


class KnowledgeBaseInput(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=500)


class MemberInput(BaseModel):
    email: EmailStr


class ChatInput(BaseModel):
    title: str | None = Field(default=None, max_length=120)
    knowledge_base_id: UUID | None = None
    use_reference: bool = True


class ChatUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=120)
    knowledge_base_id: UUID | None = None
    use_reference: bool | None = None


class MessageInput(BaseModel):
    content: str = Field(min_length=1, max_length=12000)


class HeatInputBody(BaseModel):
    voltage: float = Field(gt=0, le=100)
    current: float = Field(gt=0, le=2500)
    travel_speed_mm_min: float = Field(gt=0, le=20000)
    process: str = Field(min_length=2, max_length=8)


class CompositionBody(BaseModel):
    C: float = Field(ge=0, le=5)
    Mn: float = Field(ge=0, le=30)
    Si: float = Field(default=0, ge=0, le=10)
    Cr: float = Field(default=0, ge=0, le=30)
    Mo: float = Field(default=0, ge=0, le=10)
    V: float = Field(default=0, ge=0, le=10)
    Ni: float = Field(default=0, ge=0, le=30)
    Cu: float = Field(default=0, ge=0, le=10)
    B: float = Field(default=0, ge=0, le=1)


class PreheatBody(BaseModel):
    cet: float = Field(gt=0, le=2)
    thickness_mm: float = Field(gt=0, le=500)
    hydrogen_ml_100g: float = Field(gt=0, le=100)
    heat_input_kj_mm: float = Field(gt=0, le=20)


def _set_session(response: JSONResponse, user_id: str) -> JSONResponse:
    response.set_cookie(
        COOKIE_NAME, create_token(user_id), httponly=True, secure=False,
        samesite="lax", max_age=settings.jwt_expire_hours * 3600, path="/",
    )
    return response


app.include_router(jobs_router)


@app.on_event("startup")
def startup() -> None:
    Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)
    initialize_database()
    jwt_secret()


@app.get("/api/health")
def health() -> dict:
    with connection() as conn:
        conn.execute("SELECT 1")
    return {"status": "ok", "ollama_available": llm.available(),
            "chat_model": settings.chat_model, "embedding_model": settings.embedding_model}


@app.post("/api/auth/register")
def register(body: Credentials):
    if not settings.registration_enabled:
        raise HTTPException(status_code=403, detail="Registration is disabled")
    with connection() as conn:
        existing = conn.execute("SELECT id FROM users WHERE lower(email)=lower(%s)", (body.email,)).fetchone()
        if existing:
            raise HTTPException(status_code=409, detail="An account with this email already exists")
        user = conn.execute(
            """INSERT INTO users(email, display_name, password_hash)
               VALUES(lower(%s), %s, %s) RETURNING id, email, display_name""",
            (body.email, body.display_name.strip(), hash_password(body.password)),
        ).fetchone()
        conn.commit()
    return _set_session(JSONResponse(jsonable_encoder({"user": user})), str(user["id"]))


@app.post("/api/auth/login")
def login(body: LoginInput):
    with connection() as conn:
        user = conn.execute(
            "SELECT id,email,display_name,password_hash FROM users WHERE lower(email)=lower(%s)",
            (body.email,),
        ).fetchone()
    if not user or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    profile = {"id": user["id"], "email": user["email"], "display_name": user["display_name"]}
    return _set_session(JSONResponse(jsonable_encoder({"user": profile})), str(user["id"]))


@app.post("/api/auth/logout")
def logout():
    response = JSONResponse({"ok": True})
    response.delete_cookie(COOKIE_NAME, path="/", httponly=True, samesite="lax")
    return response


@app.get("/api/auth/me")
def me(user: dict = User):
    return {"user": user}


@app.get("/api/knowledge-bases")
def list_knowledge_bases(user: dict = User):
    with connection() as conn:
        rows = conn.execute(
            """SELECT kb.id,kb.name,kb.description,kb.created_at,kb.is_reference,
                      COALESCE(m.role, 'reader') AS role,
                      (SELECT count(*) FROM documents d WHERE d.knowledge_base_id=kb.id) AS document_count
               FROM knowledge_bases kb
               LEFT JOIN kb_members m ON m.kb_id=kb.id AND m.user_id=%s
               WHERE m.user_id IS NOT NULL OR kb.is_reference
               ORDER BY kb.is_reference, kb.created_at DESC""",
            (user["id"],),
        ).fetchall()
    return {"knowledge_bases": rows}


@app.post("/api/knowledge-bases", status_code=201)
def create_knowledge_base(body: KnowledgeBaseInput, user: dict = User):
    with connection() as conn:
        kb = conn.execute(
            "INSERT INTO knowledge_bases(name,description,created_by) VALUES(%s,%s,%s) RETURNING *",
            (body.name.strip(), body.description.strip(), user["id"]),
        ).fetchone()
        conn.execute("INSERT INTO kb_members(kb_id,user_id,role) VALUES(%s,%s,'owner')", (kb["id"], user["id"]))
        conn.commit()
    return {"knowledge_base": {**kb, "role": "owner", "document_count": 0}}


@app.get("/api/knowledge-bases/{kb_id}")
def get_knowledge_base(kb_id: UUID, user: dict = User):
    kb = require_kb_access(user["id"], str(kb_id))
    return {"knowledge_base": kb}


@app.delete("/api/knowledge-bases/{kb_id}")
def delete_knowledge_base(kb_id: UUID, user: dict = User):
    kb = require_kb_access(user["id"], str(kb_id))
    if kb["role"] != "owner":
        raise HTTPException(status_code=403, detail="Only the owner can delete this knowledge base")
    with connection() as conn:
        documents = conn.execute(
            "SELECT id, storage_path FROM documents WHERE knowledge_base_id=%s", (kb_id,)
        ).fetchall()
        conn.execute("DELETE FROM knowledge_bases WHERE id=%s", (kb_id,))
        conn.commit()
    for document in documents:
        remove_document_files(document)
    return {"ok": True}


@app.post("/api/knowledge-bases/{kb_id}/members")
def add_kb_member(kb_id: UUID, body: MemberInput, user: dict = User):
    kb = require_kb_access(user["id"], str(kb_id))
    if kb["role"] != "owner":
        raise HTTPException(status_code=403, detail="Only the owner can invite members")
    with connection() as conn:
        member = conn.execute("SELECT id FROM users WHERE lower(email)=lower(%s)", (body.email,)).fetchone()
        if not member:
            raise HTTPException(status_code=404, detail="User must create an account before being added")
        conn.execute(
            "INSERT INTO kb_members(kb_id,user_id,role) VALUES(%s,%s,'member') ON CONFLICT DO NOTHING",
            (kb_id, member["id"]),
        )
        conn.commit()
    return {"ok": True}


@app.get("/api/knowledge-bases/{kb_id}/memory")
def list_memory(kb_id: UUID, user: dict = User):
    require_kb_access(user["id"], str(kb_id))
    return {"entries": memory.list_entries(kb_id)}


@app.delete("/api/knowledge-bases/{kb_id}/memory/{entry_id}")
def delete_memory_entry(kb_id: UUID, entry_id: int, user: dict = User):
    require_kb_write(user["id"], str(kb_id))
    with connection() as conn:
        deleted = conn.execute(
            "DELETE FROM memory_entries WHERE id=%s AND knowledge_base_id=%s RETURNING id", (entry_id, kb_id)
        ).fetchone()
        conn.commit()
    if not deleted:
        raise HTTPException(status_code=404, detail="Memory entry not found")
    return {"ok": True}


@app.post("/api/knowledge-bases/{kb_id}/documents", status_code=202)
def upload_to_knowledge_base(kb_id: UUID, files: Annotated[list[UploadFile], File()], user: dict = User):
    require_kb_write(user["id"], str(kb_id))
    return {"documents": save_uploads(files, user["id"], kb_id=kb_id)}


@app.get("/api/knowledge-bases/{kb_id}/documents")
def list_documents(kb_id: UUID, user: dict = User):
    require_kb_access(user["id"], str(kb_id))
    with connection() as conn:
        rows = conn.execute(
            f"""SELECT {",".join(DOCUMENT_COLUMNS)}
               FROM documents WHERE knowledge_base_id=%s ORDER BY created_at DESC""", (kb_id,)
        ).fetchall()
    return {"documents": rows}


def _get_chat(chat_id: UUID, user_id: UUID) -> dict:
    with connection() as conn:
        chat = conn.execute("SELECT * FROM chats WHERE id=%s AND user_id=%s", (chat_id, user_id)).fetchone()
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    return chat


@app.get("/api/chats")
def list_chats(user: dict = User):
    with connection() as conn:
        rows = conn.execute(
            """SELECT c.id,c.title,c.knowledge_base_id,c.created_at,c.updated_at,k.name AS knowledge_base_name,
                      (SELECT content FROM messages m WHERE m.chat_id=c.id ORDER BY m.created_at LIMIT 1) AS first_message
               FROM chats c LEFT JOIN knowledge_bases k ON k.id=c.knowledge_base_id
               WHERE c.user_id=%s ORDER BY c.updated_at DESC""", (user["id"],)
        ).fetchall()
    return {"chats": rows}


@app.post("/api/chats", status_code=201)
def create_chat(body: ChatInput, user: dict = User):
    if body.knowledge_base_id:
        require_kb_access(user["id"], str(body.knowledge_base_id))
    with connection() as conn:
        chat = conn.execute(
            "INSERT INTO chats(user_id,title,knowledge_base_id,use_reference) VALUES(%s,%s,%s,%s) RETURNING *",
            (user["id"], body.title or "New chat", body.knowledge_base_id, body.use_reference),
        ).fetchone()
        conn.commit()
    return {"chat": chat}


@app.get("/api/chats/{chat_id}")
def get_chat(chat_id: UUID, user: dict = User):
    chat = _get_chat(chat_id, user["id"])
    with connection() as conn:
        messages = conn.execute(
            """SELECT id,role,content,citations,confidence,diagram,created_at
               FROM messages WHERE chat_id=%s ORDER BY created_at""",
            (chat_id,),
        ).fetchall()
        documents = conn.execute(
            f"""SELECT {",".join(DOCUMENT_COLUMNS)}
               FROM documents WHERE conversation_id=%s ORDER BY created_at""", (chat_id,)
        ).fetchall()
    if chat["knowledge_base_id"]:
        require_kb_access(user["id"], str(chat["knowledge_base_id"]))
    return {"chat": chat, "messages": messages, "documents": documents}


@app.patch("/api/chats/{chat_id}")
def update_chat(chat_id: UUID, body: ChatUpdate, user: dict = User):
    existing = _get_chat(chat_id, user["id"])
    if body.knowledge_base_id:
        require_kb_access(user["id"], str(body.knowledge_base_id))
    knowledge_base_id = (
        body.knowledge_base_id
        if "knowledge_base_id" in body.model_fields_set
        else existing["knowledge_base_id"]
    )
    with connection() as conn:
        chat = conn.execute(
            """UPDATE chats SET title=COALESCE(%s,title), knowledge_base_id=%s,
                   use_reference=COALESCE(%s,use_reference), updated_at=now()
               WHERE id=%s RETURNING *""",
            (body.title, knowledge_base_id, body.use_reference, chat_id),
        ).fetchone()
        conn.commit()
    return {"chat": chat}


@app.delete("/api/chats/{chat_id}")
def delete_chat(chat_id: UUID, user: dict = User):
    _get_chat(chat_id, user["id"])
    with connection() as conn:
        documents = conn.execute(
            "SELECT id, storage_path FROM documents WHERE conversation_id=%s", (chat_id,)
        ).fetchall()
        conn.execute("DELETE FROM chats WHERE id=%s", (chat_id,))
        conn.commit()
    for document in documents:
        remove_document_files(document)
    return {"ok": True}


@app.post("/api/chats/{chat_id}/documents", status_code=202)
def upload_to_chat(chat_id: UUID, files: Annotated[list[UploadFile], File()], user: dict = User):
    _get_chat(chat_id, user["id"])
    return {"documents": save_uploads(files, user["id"], chat_id=chat_id)}


def _visible_document(document_id: UUID, user: dict) -> dict:
    """The document if this user may see it: a member of its knowledge base, or the owner of its chat."""
    with connection() as conn:
        doc = conn.execute(
            """SELECT d.*, c.user_id AS chat_owner FROM documents d
               LEFT JOIN chats c ON c.id = d.conversation_id WHERE d.id=%s""",
            (document_id,),
        ).fetchone()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    if doc["knowledge_base_id"]:
        doc["kb_role"] = require_kb_access(user["id"], str(doc["knowledge_base_id"]))["role"]
    elif doc["chat_owner"] != user["id"]:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


@app.delete("/api/documents/{document_id}")
def delete_document(document_id: UUID, user: dict = User):
    doc = _visible_document(document_id, user)
    if doc["knowledge_base_id"] and doc.get("kb_role") != "owner" and doc["uploaded_by"] != user["id"]:
        raise HTTPException(status_code=403, detail="Only the knowledge base owner or the uploader can remove this document")
    with connection() as conn:
        conn.execute("DELETE FROM documents WHERE id=%s", (document_id,))
        conn.commit()
    remove_document_files(doc)
    return {"ok": True}


@app.get("/api/documents/{document_id}/file")
def download_document(document_id: UUID, user: dict = User):
    doc = _visible_document(document_id, user)
    # inline, so the viewer (and a new tab) can render it instead of downloading it
    return FileResponse(doc["storage_path"], filename=doc["filename"], media_type=doc["content_type"],
                        content_disposition_type="inline")


@app.get("/api/figures/{figure_id}")
def get_figure(figure_id: int, user: dict = User):
    with connection() as conn:
        figure = conn.execute("SELECT document_id, image_path, media_type FROM figures WHERE id=%s", (figure_id,)).fetchone()
    if not figure:
        raise HTTPException(status_code=404, detail="Figure not found")
    _visible_document(figure["document_id"], user)
    return FileResponse(figure["image_path"], media_type=figure["media_type"])


def _calculate(function, body: BaseModel) -> dict:
    try:
        return function(**body.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/calc/heat-input")
def calc_heat_input(body: HeatInputBody, user: dict = User):
    return _calculate(welding.heat_input, body)


@app.post("/api/calc/carbon-equivalent")
def calc_carbon_equivalent(body: CompositionBody, user: dict = User):
    return _calculate(welding.carbon_equivalent, body)


@app.post("/api/calc/preheat")
def calc_preheat(body: PreheatBody, user: dict = User):
    return _calculate(welding.preheat_cet, body)


@app.post("/api/chats/{chat_id}/messages")
def send_message(chat_id: UUID, body: MessageInput, user: dict = User):
    chat = _get_chat(chat_id, user["id"])
    if chat["knowledge_base_id"]:
        require_kb_access(user["id"], str(chat["knowledge_base_id"]))
    query = body.content.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Message cannot be blank")
    with connection() as conn:
        user_message = conn.execute(
            "INSERT INTO messages(chat_id,role,content) VALUES(%s,'user',%s) RETURNING id,role,content,created_at",
            (chat_id, query),
        ).fetchone()
        conn.execute(
            """UPDATE chats SET updated_at=now(), title=CASE WHEN title='New chat' THEN %s ELSE title END
               WHERE id=%s""", (query[:70], chat_id)
        )
        conn.commit()
    diagram = diagram_request(query)
    if diagram:
        stream = diagram_stream(chat, diagram)
    else:
        stream = answer_stream(chat, query, history_for_chat(str(chat_id), str(user_message["id"])))
    return StreamingResponse(
        stream,
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )
