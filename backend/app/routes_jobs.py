"""
Job files: the documents for one fabrication job, their extracted fields, and
the cross-checks between them. A job belongs to a library; reading needs
library access and changing it needs write access.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field

from app.config import settings
from app.db import connection
from app.job_checks import run_checks
from app.job_fields import (
    DOC_TYPES, EXTRACTOR_VERSION, FIELDS, PARSERS, display, extract_fields, guess_doc_type, parse_weld_log,
)
from app.security import User, require_kb_access, require_kb_write
from app.uploads import save_uploads

logger = logging.getLogger("datum.jobs")
router = APIRouter(prefix="/api")

DocType = Literal["wps", "pqr", "wpq", "consumable", "weld_log", "other"]


class JobInput(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=1000)


class JobUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=1000)


class AttachInput(BaseModel):
    document_id: UUID
    doc_type: DocType | None = None


class JobDocumentUpdate(BaseModel):
    doc_type: DocType | None = None
    # field key -> corrected value as text; null clears a wrong extraction; "" removes the correction
    overrides: dict[str, str | None] | None = None


def _job(job_id: UUID, user: dict, write: bool = False) -> dict:
    with connection() as conn:
        job = conn.execute("SELECT * FROM jobs WHERE id=%s", (job_id,)).fetchone()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    (require_kb_write if write else require_kb_access)(user["id"], str(job["knowledge_base_id"]))
    return job


def _summary(job: dict, document_count: int = 0) -> dict:
    check = job.get("last_check") or {}
    return {"id": job["id"], "knowledge_base_id": job["knowledge_base_id"], "name": job["name"],
            "description": job["description"], "checked_at": job["checked_at"], "counts": check.get("counts"),
            "document_count": document_count, "created_at": job["created_at"], "updated_at": job["updated_at"]}


def _apply_overrides(doc_type: str, fields: dict, overrides: dict) -> dict:
    specs = {field.key: field for field in FIELDS.get(doc_type, ())}
    effective = dict(fields)
    for key, override in (overrides or {}).items():
        if key not in specs:
            continue
        if override.get("raw") is None:
            effective.pop(key, None)
            continue
        value = PARSERS[specs[key].kind](override["raw"])
        effective[key] = {"value": value, "raw": override["raw"], "page": None, "locator": "entered by hand",
                          "snippet": f"{specs[key].label}: {override['raw']} (entered by {override.get('by', 'a user')})", "method": "user"}
    return effective


def _load_documents(job_id: UUID, refresh: bool = True) -> list[dict]:
    """The job's documents with effective fields, extracting any that are new or re-indexed."""
    with connection() as conn:
        rows = conn.execute(
            """SELECT jd.doc_type, jd.overrides, jd.extracted, jd.extracted_for, d.id AS document_id, d.filename,
                      d.status, d.error_message, d.updated_at, d.storage_path, d.page_count, d.content_type
               FROM job_documents jd JOIN documents d ON d.id=jd.document_id
               WHERE jd.job_id=%s ORDER BY jd.added_at""",
            (job_id,),
        ).fetchall()
    documents = []
    for row in rows:
        extracted = row["extracted"]
        stale = extracted is None or row["extracted_for"] != row["updated_at"] or extracted.get("version") != EXTRACTOR_VERSION
        if refresh and row["status"] == "ready" and row["doc_type"] != "other" and stale:
            extracted = _extract(row)
            with connection() as conn:
                conn.execute("UPDATE job_documents SET extracted=%s, extracted_for=%s WHERE job_id=%s AND document_id=%s",
                             (Jsonb(extracted), row["updated_at"], job_id, row["document_id"]))
                conn.commit()
        extracted = extracted or {}
        documents.append({
            "document_id": str(row["document_id"]), "filename": row["filename"], "doc_type": row["doc_type"],
            "status": row["status"], "error_message": row["error_message"], "page_count": row["page_count"],
            "content_type": row["content_type"], "overrides": row["overrides"] or {},
            "fields": _apply_overrides(row["doc_type"], extracted.get("fields", {}), row["overrides"] or {}),
            "log": extracted.get("log"), "log_error": extracted.get("log_error"),
        })
    return documents


def _extract(row: dict) -> dict:
    if row["doc_type"] == "weld_log":
        try:
            return {"version": EXTRACTOR_VERSION, "log": parse_weld_log(row["storage_path"])}
        except Exception as exc:  # unreadable or not a log: report it as a finding, don't fail the job
            return {"version": EXTRACTOR_VERSION, "log_error": str(exc)[:300]}
    return {"version": EXTRACTOR_VERSION,
            "fields": extract_fields(row["document_id"], row["doc_type"], use_model=settings.extraction_model_fallback)}


def _public_document(document: dict) -> dict:
    specs = FIELDS.get(document["doc_type"], ())
    fields = [{
        "key": field.key, "label": field.label, "kind": field.kind, "required": field.required,
        "display": display(field.kind, document["fields"][field.key]["value"]) if field.key in document["fields"] else None,
        "source": {k: document["fields"][field.key].get(k) for k in ("page", "locator", "snippet", "method", "raw")} if field.key in document["fields"] else None,
        "overridden": field.key in document["overrides"],
    } for field in specs]
    log = document.get("log")
    return {
        "document_id": document["document_id"], "filename": document["filename"], "doc_type": document["doc_type"],
        "status": document["status"], "error_message": document["error_message"], "page_count": document["page_count"],
        "fields": fields,
        "log": {"rows": len(log["rows"]), "columns": log["columns"], "sheet": log["sheet"]} if log else None,
        "log_error": document.get("log_error"),
    }


@router.get("/knowledge-bases/{kb_id}/jobs")
def list_jobs(kb_id: UUID, user: dict = User):
    require_kb_access(user["id"], str(kb_id))
    with connection() as conn:
        jobs = conn.execute(
            """SELECT j.*, (SELECT count(*) FROM job_documents jd WHERE jd.job_id=j.id) AS document_count
               FROM jobs j WHERE j.knowledge_base_id=%s ORDER BY j.updated_at DESC""",
            (kb_id,),
        ).fetchall()
    return {"jobs": [_summary(job, job["document_count"]) for job in jobs], "doc_types": DOC_TYPES}


@router.post("/knowledge-bases/{kb_id}/jobs", status_code=201)
def create_job(kb_id: UUID, body: JobInput, user: dict = User):
    require_kb_write(user["id"], str(kb_id))
    with connection() as conn:
        job = conn.execute(
            "INSERT INTO jobs(knowledge_base_id, name, description, created_by) VALUES(%s,%s,%s,%s) RETURNING *",
            (kb_id, body.name.strip(), body.description.strip(), user["id"]),
        ).fetchone()
        conn.commit()
    return {"job": _summary(job)}


@router.get("/jobs/{job_id}")
def get_job(job_id: UUID, user: dict = User):
    job = _job(job_id, user)
    documents = _load_documents(job_id)
    return {"job": _summary(job, len(documents)), "documents": [_public_document(d) for d in documents],
            "check": job["last_check"], "doc_types": DOC_TYPES}


@router.patch("/jobs/{job_id}")
def update_job(job_id: UUID, body: JobUpdate, user: dict = User):
    _job(job_id, user, write=True)
    with connection() as conn:
        job = conn.execute(
            """UPDATE jobs SET name=COALESCE(%s,name), description=COALESCE(%s,description), updated_at=now()
               WHERE id=%s RETURNING *""",
            (body.name, body.description, job_id),
        ).fetchone()
        conn.commit()
    return {"job": _summary(job)}


@router.delete("/jobs/{job_id}")
def delete_job(job_id: UUID, user: dict = User):
    _job(job_id, user, write=True)
    with connection() as conn:
        conn.execute("DELETE FROM jobs WHERE id=%s", (job_id,))
        conn.commit()
    return {"ok": True}


def _attach(job: dict, document_id: UUID, doc_type: str | None) -> None:
    with connection() as conn:
        document = conn.execute(
            "SELECT id, filename, knowledge_base_id FROM documents WHERE id=%s", (document_id,)
        ).fetchone()
        if not document or document["knowledge_base_id"] != job["knowledge_base_id"]:
            raise HTTPException(status_code=404, detail="That document isn't in this job's library")
        first = conn.execute("SELECT content FROM chunks WHERE document_id=%s ORDER BY chunk_index LIMIT 1", (document_id,)).fetchone()
        doc_type = doc_type or guess_doc_type(document["filename"], first["content"] if first else "")
        conn.execute(
            """INSERT INTO job_documents(job_id, document_id, doc_type) VALUES(%s,%s,%s)
               ON CONFLICT (job_id, document_id) DO UPDATE SET doc_type=EXCLUDED.doc_type, extracted=NULL""",
            (job["id"], document_id, doc_type),
        )
        conn.execute("UPDATE jobs SET updated_at=now() WHERE id=%s", (job["id"],))
        conn.commit()


@router.post("/jobs/{job_id}/documents", status_code=201)
def attach_document(job_id: UUID, body: AttachInput, user: dict = User):
    job = _job(job_id, user, write=True)
    _attach(job, body.document_id, body.doc_type)
    return {"ok": True}


@router.post("/jobs/{job_id}/upload", status_code=202)
def upload_to_job(job_id: UUID, files: Annotated[list[UploadFile], File()], doc_type: Annotated[str | None, Form()] = None, user: dict = User):
    """Adds the files to the job's library and attaches them; the type is guessed from each file unless given."""
    job = _job(job_id, user, write=True)
    if doc_type is not None and doc_type not in DOC_TYPES:
        raise HTTPException(status_code=422, detail=f"Unknown document type {doc_type}")
    saved = save_uploads(files, user["id"], kb_id=job["knowledge_base_id"])
    for document in saved:
        if document.get("id"):
            _attach(job, document["id"], doc_type)
    return {"documents": saved}


@router.patch("/jobs/{job_id}/documents/{document_id}")
def update_job_document(job_id: UUID, document_id: UUID, body: JobDocumentUpdate, user: dict = User):
    _job(job_id, user, write=True)
    with connection() as conn:
        link = conn.execute("SELECT doc_type, overrides FROM job_documents WHERE job_id=%s AND document_id=%s",
                            (job_id, document_id)).fetchone()
        if not link:
            raise HTTPException(status_code=404, detail="That document isn't in this job")
        doc_type = body.doc_type or link["doc_type"]
        overrides = dict(link["overrides"] or {}) if doc_type == link["doc_type"] else {}
        specs = {field.key: field for field in FIELDS.get(doc_type, ())}
        for key, raw in (body.overrides or {}).items():
            if key not in specs:
                raise HTTPException(status_code=422, detail=f"{DOC_TYPES[doc_type]} has no field {key}")
            if raw == "":
                overrides.pop(key, None)
                continue
            if raw is not None and PARSERS[specs[key].kind](raw) in (None, [], ""):
                raise HTTPException(status_code=422, detail=f"Couldn't read {raw!r} as {specs[key].label.lower()}")
            overrides[key] = {"raw": raw, "by": user["display_name"], "at": datetime.now(timezone.utc).isoformat()}
        conn.execute(
            """UPDATE job_documents SET doc_type=%s, overrides=%s,
                      extracted=CASE WHEN %s THEN NULL ELSE extracted END
               WHERE job_id=%s AND document_id=%s""",
            (doc_type, Jsonb(overrides), doc_type != link["doc_type"], job_id, document_id),
        )
        conn.execute("UPDATE jobs SET updated_at=now() WHERE id=%s", (job_id,))
        conn.commit()
    return {"ok": True}


@router.delete("/jobs/{job_id}/documents/{document_id}")
def detach_document(job_id: UUID, document_id: UUID, user: dict = User):
    """Removes the document from the job; it stays in the library."""
    _job(job_id, user, write=True)
    with connection() as conn:
        conn.execute("DELETE FROM job_documents WHERE job_id=%s AND document_id=%s", (job_id, document_id))
        conn.execute("UPDATE jobs SET updated_at=now() WHERE id=%s", (job_id,))
        conn.commit()
    return {"ok": True}


@router.post("/jobs/{job_id}/check")
def check_job(job_id: UUID, user: dict = User):
    _job(job_id, user)
    documents = _load_documents(job_id)
    ready = [document for document in documents if document["status"] == "ready" and document["doc_type"] != "other"]
    result = run_checks(ready)
    result["pending"] = [{"document_id": d["document_id"], "filename": d["filename"], "status": d["status"]}
                         for d in documents if d["status"] != "ready"]
    with connection() as conn:
        conn.execute("UPDATE jobs SET last_check=%s, checked_at=now() WHERE id=%s", (Jsonb(result), job_id))
        conn.commit()
    return {"check": result, "checked_at": datetime.now(timezone.utc).isoformat()}
