"""
Hybrid retrieval = vector search (semantic) + BM25 (exact keyword match),
fused with Reciprocal Rank Fusion.

Why this matters for technical docs specifically: a question like "what is
the max voltage of the LM317" needs the exact token "LM317" to hit - pure
embedding similarity can drift toward semantically-similar-but-wrong parts.
BM25 catches the exact term; vector search catches paraphrased questions.
Together they cover both failure modes.

BM25 index is built on-demand from the tenant's own collection (scoped the
same way as everything else - no cross-tenant leakage risk since we only
ever pull documents from one collection).
"""
from rank_bm25 import BM25Okapi
from app.core.vectorstore import get_collection, query as vector_query


def _tokenize(text: str) -> list[str]:
    return text.lower().split()


def _bm25_search(user_id: str, project_id: str, question: str, top_k: int) -> list[dict]:
    col = get_collection(user_id, project_id)
    if col.count() == 0:
        return []

    all_docs = col.get(include=["documents", "metadatas"])
    corpus = all_docs["documents"]
    metadatas = all_docs["metadatas"]
    if not corpus:
        return []

    tokenized_corpus = [_tokenize(d) for d in corpus]
    bm25 = BM25Okapi(tokenized_corpus)
    scores = bm25.get_scores(_tokenize(question))

    ranked_idx = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]
    return [
        {"text": corpus[i], "metadata": metadatas[i], "score": float(scores[i])}
        for i in ranked_idx if scores[i] > 0
    ]


RRF_K = 60  # standard RRF damping constant; also bounds the max fusion score


def _reciprocal_rank_fusion(result_lists: list[list[dict]], k: int = RRF_K) -> list[dict]:
    """
    Standard RRF: score = sum(1 / (k + rank)) across each ranked list a
    passage appears in. Passages found by BOTH methods naturally rise to
    the top - that's the signal we want.
    """
    fused_scores: dict[str, float] = {}
    passage_by_key: dict[str, dict] = {}

    for results in result_lists:
        for rank, item in enumerate(results):
            key = item["text"]  # chunk text as dedup key
            fused_scores[key] = fused_scores.get(key, 0.0) + 1.0 / (k + rank + 1)
            passage_by_key[key] = item

    ordered_keys = sorted(fused_scores, key=lambda k_: fused_scores[k_], reverse=True)
    out = []
    for key in ordered_keys:
        item = dict(passage_by_key[key])
        item["fusion_score"] = fused_scores[key]
        out.append(item)
    return out


def hybrid_search(user_id: str, project_id: str, question: str, q_embedding: list[float], top_k: int) -> list[dict]:
    vector_results = vector_query(user_id, project_id, q_embedding, top_k)
    keyword_results = _bm25_search(user_id, project_id, question, top_k)
    fused = _reciprocal_rank_fusion([vector_results, keyword_results])
    return fused[:top_k]
