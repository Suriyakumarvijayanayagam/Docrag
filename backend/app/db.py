from contextlib import contextmanager

import psycopg
from pgvector.psycopg import register_vector
from psycopg.rows import dict_row

from app.config import settings


SCHEMA = """
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS knowledge_bases (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    created_by UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS kb_members (
    kb_id UUID NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role TEXT NOT NULL DEFAULT 'member' CHECK (role IN ('owner', 'member')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (kb_id, user_id)
);

CREATE TABLE IF NOT EXISTS chats (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    knowledge_base_id UUID REFERENCES knowledge_bases(id) ON DELETE SET NULL,
    title TEXT NOT NULL DEFAULT 'New chat',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    knowledge_base_id UUID REFERENCES knowledge_bases(id) ON DELETE CASCADE,
    conversation_id UUID REFERENCES chats(id) ON DELETE CASCADE,
    uploaded_by UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    filename TEXT NOT NULL,
    content_type TEXT NOT NULL,
    byte_size BIGINT NOT NULL,
    sha256 TEXT NOT NULL,
    storage_path TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'indexing', 'ready', 'failed')),
    error_message TEXT,
    page_count INTEGER NOT NULL DEFAULT 0,
    chunk_count INTEGER NOT NULL DEFAULT 0,
    parser_version TEXT NOT NULL DEFAULT '0',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK ((knowledge_base_id IS NOT NULL AND conversation_id IS NULL) OR
           (knowledge_base_id IS NULL AND conversation_id IS NOT NULL))
);

CREATE UNIQUE INDEX IF NOT EXISTS documents_kb_hash_unique
    ON documents(knowledge_base_id, sha256) WHERE knowledge_base_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS documents_kb_status_idx ON documents(knowledge_base_id, status);
CREATE INDEX IF NOT EXISTS documents_chat_idx ON documents(conversation_id);

CREATE TABLE IF NOT EXISTS ingestion_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL UNIQUE REFERENCES documents(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'running', 'done', 'failed')),
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS chunks (
    id BIGSERIAL PRIMARY KEY,
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    token_count INTEGER NOT NULL,
    page_start INTEGER,
    page_end INTEGER,
    section TEXT NOT NULL DEFAULT '',
    embedding vector(%(embedding_dim)s),
    search_vector TSVECTOR GENERATED ALWAYS AS (to_tsvector('simple', content)) STORED,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(document_id, chunk_index)
);
CREATE INDEX IF NOT EXISTS chunks_search_idx ON chunks USING GIN(search_vector);
CREATE INDEX IF NOT EXISTS chunks_embedding_idx ON chunks USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS chunks_document_idx ON chunks(document_id);

CREATE TABLE IF NOT EXISTS messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chat_id UUID NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    citations JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS messages_chat_created_idx ON messages(chat_id, created_at);
ALTER TABLE messages ADD COLUMN IF NOT EXISTS confidence TEXT;
ALTER TABLE messages ADD COLUMN IF NOT EXISTS diagram JSONB;

ALTER TABLE documents ADD COLUMN IF NOT EXISTS fact_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS figure_count INTEGER NOT NULL DEFAULT 0;

-- Table cells as exact label/value pairs, looked up before semantic retrieval.
-- Scoped through documents, so deleting a document removes its facts.
CREATE TABLE IF NOT EXISTS structured_facts (
    id BIGSERIAL PRIMARY KEY,
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    page INTEGER,
    locator TEXT NOT NULL,
    label TEXT NOT NULL,
    value TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS structured_facts_document_idx ON structured_facts(document_id);

-- Images embedded in source documents. The rows cascade with the document;
-- the image files are removed by storage.remove_document_files.
CREATE TABLE IF NOT EXISTS figures (
    id BIGSERIAL PRIMARY KEY,
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    page INTEGER,
    locator TEXT NOT NULL,
    caption TEXT NOT NULL,
    image_path TEXT NOT NULL,
    media_type TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS figures_document_idx ON figures(document_id);

-- Distilled facts/decisions/preferences, shared by everyone with access to the
-- knowledge base. Not raw chat logs - see memory.distill_exchange.
CREATE TABLE IF NOT EXISTS memory_entries (
    id BIGSERIAL PRIMARY KEY,
    knowledge_base_id UUID NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
    entry_type TEXT NOT NULL CHECK (entry_type IN ('fact', 'decision', 'preference')),
    content TEXT NOT NULL,
    source_chat_id UUID REFERENCES chats(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS memory_entries_kb_idx ON memory_entries(knowledge_base_id, created_at);

-- Reference libraries (standards, codes, catalogues) are loaded by the server
-- operator with scripts/load_reference.py and readable by every account. They
-- have no owner and their documents no uploader.
ALTER TABLE knowledge_bases ADD COLUMN IF NOT EXISTS is_reference BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE knowledge_bases ALTER COLUMN created_by DROP NOT NULL;
ALTER TABLE documents ALTER COLUMN uploaded_by DROP NOT NULL;
-- Whether a thread also searches the reference libraries.
ALTER TABLE chats ADD COLUMN IF NOT EXISTS use_reference BOOLEAN NOT NULL DEFAULT true;
"""

# Bump whenever extraction changes in a way existing documents should pick up
# (new block format, facts, figures). Stale documents are re-queued on startup.
PARSER_VERSION = "3"
SCHEMA_LOCK_ID = 7_314_202_601


def connect() -> psycopg.Connection:
    conn = psycopg.connect(settings.database_url, row_factory=dict_row)
    register_vector(conn)
    return conn


@contextmanager
def connection():
    conn = connect()
    try:
        yield conn
    finally:
        conn.close()


def initialize_database() -> None:
    statements = SCHEMA.replace("%(embedding_dim)s", str(settings.embedding_dim))
    # pgvector's adapter cannot register its type until the extension exists.
    conn = psycopg.connect(settings.database_url, row_factory=dict_row)
    try:
        # The API and the worker both run this at startup; on a fresh database
        # two concurrent CREATE EXTENSIONs collide, so take turns. Session-level
        # lock, released when the connection closes.
        conn.execute("SELECT pg_advisory_lock(%s)", (SCHEMA_LOCK_ID,))
        conn.execute(statements)
        conn.commit()

        stale = conn.execute(
            """UPDATE documents
               SET status='queued', error_message=NULL, updated_at=now()
               WHERE parser_version <> %s AND status IN ('ready', 'failed')
               RETURNING id""",
            (PARSER_VERSION,),
        ).fetchall()
        for document in stale:
            conn.execute(
                """INSERT INTO ingestion_jobs(document_id, status, attempts, last_error)
                   VALUES(%s, 'queued', 0, NULL)
                   ON CONFLICT(document_id) DO UPDATE
                   SET status='queued', attempts=0, last_error=NULL, updated_at=now()""",
                (document["id"],),
            )
        conn.commit()
    finally:
        conn.close()
