"""
Multi-tenant isolation lives HERE, at the storage layer - not as an
afterthought metadata filter. Each (user_id, project_id) pair gets its own
physical Chroma collection. There is no code path that can query across
collections, so cross-user leakage is structurally prevented, not just
policy-prevented.
"""
import hashlib
import re
import chromadb
from app.config import settings

_client = chromadb.PersistentClient(path=settings.chroma_path)


# Chroma also requires the name to start and end with an alphanumeric and to
# contain no consecutive periods - a project id ending in "-" or "_" (or one
# long enough to be truncated onto a separator) produces a name Chroma rejects,
# which surfaced as a 500 rather than an empty result.
_VALID_COLLECTION = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{1,61}[a-zA-Z0-9]$")


def _collection_name(user_id: str, project_id: str) -> str:
    # Chroma collection names are restricted to [a-zA-Z0-9._-], 3-63 chars.
    safe = re.sub(r"[^a-zA-Z0-9._-]", "_", f"u_{user_id}__p_{project_id}")[:63]

    if _VALID_COLLECTION.match(safe) and ".." not in safe:
        return safe

    # Fall back to a hashed name for tenant keys that can't be expressed
    # directly. Keyed on the raw ids with a separator, so two different tenants
    # can never collide, and only applied when the direct name is invalid so
    # existing collections keep their current names.
    digest = hashlib.sha1(f"{user_id}\x00{project_id}".encode()).hexdigest()[:16]
    return f"t_{digest}"


def get_collection(user_id: str, project_id: str):
    name = _collection_name(user_id, project_id)
    return _client.get_or_create_collection(name=name, metadata={"hnsw:space": "cosine"})


def add_chunks(user_id: str, project_id: str, doc_id: str, chunks: list[dict], embeddings: list[list[float]]):
    """
    chunks: list of {"text": ..., "page"/"section": N, "chunk_index": M}
    embeddings: parallel list of embedding vectors
    """
    col = get_collection(user_id, project_id)
    ids = [f"{doc_id}_{i}" for i in range(len(chunks))]
    metadatas = [{"doc_id": doc_id, **{k: v for k, v in c.items() if k != "text"}} for c in chunks]
    documents = [c["text"] for c in chunks]
    col.add(ids=ids, embeddings=embeddings, metadatas=metadatas, documents=documents)


def query(user_id: str, project_id: str, query_embedding: list[float], top_k: int) -> list[dict]:
    col = get_collection(user_id, project_id)
    if col.count() == 0:
        return []
    res = col.query(query_embeddings=[query_embedding], n_results=min(top_k, col.count()))
    out = []
    for doc, meta, dist in zip(res["documents"][0], res["metadatas"][0], res["distances"][0]):
        out.append({"text": doc, "metadata": meta, "score": 1 - dist})
    return out


def delete_document(user_id: str, project_id: str, doc_id: str):
    col = get_collection(user_id, project_id)
    col.delete(where={"doc_id": doc_id})


def list_documents(user_id: str, project_id: str) -> list[dict]:
    """
    The documents in this tenant, rebuilt from chunk metadata - Chroma is the
    only place that knows what has been ingested, so a client that reconnects
    (or just reloads) can recover the document list instead of only knowing
    about uploads it performed itself.
    """
    col = get_collection(user_id, project_id)
    if col.count() == 0:
        return []

    docs: dict[str, dict] = {}
    for meta in col.get(include=["metadatas"])["metadatas"] or []:
        doc_id = meta.get("doc_id") if meta else None
        if not doc_id:
            continue
        entry = docs.setdefault(
            doc_id,
            {"doc_id": doc_id, "filename": meta.get("source_file") or "unknown", "chunk_count": 0},
        )
        entry["chunk_count"] += 1
    return list(docs.values())


def project_doc_count(user_id: str, project_id: str) -> int:
    """
    Number of distinct source documents - NOT col.count(), which counts
    chunks (a single 40-page PDF is one document but dozens of chunks).
    """
    col = get_collection(user_id, project_id)
    if col.count() == 0:
        return 0
    metas = col.get(include=["metadatas"])["metadatas"] or []
    return len({m["doc_id"] for m in metas if m and m.get("doc_id")})


def project_chunk_count(user_id: str, project_id: str) -> int:
    return get_collection(user_id, project_id).count()
