import logging
import shutil
import time
from pathlib import Path

from pgvector import Vector

from app import llm
from app.config import settings
from app.db import PARSER_VERSION, connection, initialize_database
from app.facts import extract_facts
from app.figures import extract_figures
from app.ingestion import make_chunks
from app.storage import figure_dir

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("datum.worker")


def claim_job() -> dict | None:
    with connection() as conn:
        with conn.transaction():
            job = conn.execute(
                """SELECT j.id, j.document_id, j.attempts, d.storage_path
                   FROM ingestion_jobs j JOIN documents d ON d.id = j.document_id
                   WHERE j.status = 'queued'
                      OR (j.status = 'running' AND j.updated_at < now() - interval '1 hour')
                   ORDER BY j.created_at
                   FOR UPDATE OF j SKIP LOCKED LIMIT 1"""
            ).fetchone()
            if not job:
                return None
            conn.execute(
                "UPDATE ingestion_jobs SET status='running', attempts=attempts+1, updated_at=now() WHERE id=%s",
                (job["id"],),
            )
            conn.execute(
                "UPDATE documents SET status='indexing', error_message=NULL, updated_at=now() WHERE id=%s",
                (job["document_id"],),
            )
            job["attempts"] += 1
            return job


def _optional(step: str, document_id, extract, default):
    """Facts and figures add to a document; a failure in either must not block its text from indexing."""
    try:
        return extract()
    except Exception:
        logger.exception("%s extraction failed for document %s", step, document_id)
        return default


def process_job(job: dict) -> None:
    document_id = job["document_id"]
    path = job["storage_path"]
    chunks, page_count = make_chunks(path)
    embeddings = llm.embed([chunk.content for chunk in chunks])
    facts = _optional("Fact", document_id, lambda: extract_facts(path), [])
    shutil.rmtree(figure_dir(document_id), ignore_errors=True)
    figures = _optional("Figure", document_id, lambda: extract_figures(path, document_id), [])
    try:
        with connection() as conn:
            with conn.transaction():
                conn.execute("DELETE FROM chunks WHERE document_id=%s", (document_id,))
                conn.execute("DELETE FROM structured_facts WHERE document_id=%s", (document_id,))
                conn.execute("DELETE FROM figures WHERE document_id=%s", (document_id,))
                conn.cursor().executemany(
                    """INSERT INTO chunks(document_id, chunk_index, content, token_count, page_start, page_end, section, embedding)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                    [
                        (
                            document_id, index, chunk.content, chunk.token_count,
                            chunk.page_start, chunk.page_end, chunk.section, Vector(embeddings[index]),
                        )
                        for index, chunk in enumerate(chunks)
                    ],
                )
                if facts:
                    conn.cursor().executemany(
                        "INSERT INTO structured_facts(document_id, page, locator, label, value) VALUES (%s,%s,%s,%s,%s)",
                        [(document_id, fact.page, fact.locator, fact.label[:500], fact.value[:2000]) for fact in facts],
                    )
                if figures:
                    conn.cursor().executemany(
                        """INSERT INTO figures(document_id, page, locator, caption, image_path, media_type)
                           VALUES (%s,%s,%s,%s,%s,%s)""",
                        [(document_id, figure.page, figure.locator, figure.caption, figure.image_path, figure.media_type)
                         for figure in figures],
                    )
                conn.execute(
                    """UPDATE documents SET status='ready', page_count=%s, chunk_count=%s, fact_count=%s,
                       figure_count=%s, parser_version=%s, error_message=NULL, updated_at=now() WHERE id=%s""",
                    (page_count, len(chunks), len(facts), len(figures), PARSER_VERSION, document_id),
                )
                conn.execute(
                    "UPDATE ingestion_jobs SET status='done', last_error=NULL, updated_at=now() WHERE id=%s",
                    (job["id"],),
                )
    except Exception:
        # e.g. the document was deleted mid-indexing: don't leave its images behind
        shutil.rmtree(figure_dir(document_id), ignore_errors=True)
        raise


def fail_job(job: dict, error: Exception) -> None:
    message = str(error)[:1000]
    retry = job["attempts"] < 3
    with connection() as conn:
        with conn.transaction():
            conn.execute(
                """UPDATE ingestion_jobs SET status=%s, last_error=%s, updated_at=now() WHERE id=%s""",
                ("queued" if retry else "failed", message, job["id"]),
            )
            conn.execute(
                """UPDATE documents SET status=%s, error_message=%s, updated_at=now() WHERE id=%s""",
                ("queued" if retry else "failed", message, job["document_id"]),
            )


def run() -> None:
    Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)
    initialize_database()
    logger.info("Ingestion worker started")
    while True:
        job = None
        try:
            job = claim_job()
            if not job:
                time.sleep(2)
                continue
            logger.info("Processing document %s", job["document_id"])
            process_job(job)
            logger.info("Indexed document %s", job["document_id"])
        except Exception as exc:
            logger.exception("Worker loop error: %s", exc)
            if job:
                try:
                    fail_job(job, exc)
                except Exception:
                    logger.exception("Could not record ingestion failure")
            time.sleep(2)


if __name__ == "__main__":
    run()
