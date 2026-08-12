"""
Reranking without a dedicated cross-encoder model.

A real cross-encoder (bge-reranker-base) is more accurate but pulls in
torch, which conflicts with the "stay small" goal. Instead we do single-pass
LLM-prompted relevance scoring: cheap, no extra model to manage, still
meaningfully better than trusting raw vector distance alone.

Swap this for a dedicated cross-encoder later if quality demands it - the
interface (rerank(query, candidates) -> reordered candidates) won't change.

IMPORTANT - the scores this returns are also the confidence signal shown to
the user (query_pipeline._confidence_label), so they must always be on the
documented 0-10 scale. A 2-3B model is an unreliable scorer: observed failure
modes are (a) returning passage indices instead of scores, (b) returning the
wrong number of scores, and (c) scoring every passage 0 even when one of them
states the answer. Each is handled explicitly below rather than allowed to
silently corrupt the scale.
"""
import json
import re

from app.core.hybrid_search import RRF_K
from app.core.llm_client import ollama

_RERANK_SYSTEM = """You rate how useful each numbered passage is for answering the query.

Scale:
10 = contains the answer outright
7  = contains most of the answer, or directly discusses the exact thing asked about
4  = same topic or component, useful background, but does not answer it
1  = same document, unrelated topic
0  = irrelevant

Rules:
- Output EXACTLY one score per passage, in the same order as given.
- Output ONLY a JSON array of integers, e.g. [7, 0, 10, 4]. No prose, no markdown, \
no passage numbers, no trailing text.
- Judge each passage independently. Most passages in a set are not relevant and \
should score 0 - but if a passage states the answer, it MUST score 8 or higher."""

# Highest possible RRF score: rank 0 in both the vector and BM25 lists.
_MAX_RRF = 2.0 / (RRF_K + 1)

# Ceiling for retrieval-only scores. When the LLM gives no usable judgement we
# still know the retrievers agreed, which is worth something - but it is not
# verified relevance, so it must not be able to reach the "high" band (>=7).
# Reporting "high" off retrieval agreement alone is exactly how a confident
# wrong answer gets shown to a reviewer as trustworthy.
_RETRIEVAL_ONLY_CEILING = 6.5


def _retrieval_only_scores(candidates: list[dict]) -> list[float]:
    """
    Map retrieval evidence onto the 0-10 scale, capped at the medium band.

    Uses the RRF fusion score, which is bounded (unlike raw BM25 scores - those
    are unbounded, and multiplying them by 10 previously produced "relevance
    38.5" on a 0-10 scale, reported to the user as high confidence).
    """
    out = []
    for c in candidates:
        fusion = c.get("fusion_score")
        if fusion is None:
            normalized = min(max(c.get("score", 0.0), 0.0), 1.0)  # cosine similarity
        else:
            normalized = min(fusion / _MAX_RRF, 1.0)
        out.append(round(normalized * _RETRIEVAL_ONLY_CEILING, 2))
    return out


def _parse_scores(raw: str, expected: int) -> list[float]:
    """
    Lenient parse of the model's score array. Returns [] if the output can't be
    trusted at all; otherwise always returns exactly `expected` scores.
    """
    try:
        parsed = json.loads(raw.strip())
    except Exception:
        # e.g. ```json [..] ``` or a stray sentence - take the first bare array
        match = re.search(r"\[[^\]]*\]", raw, re.S)
        if not match:
            return []
        try:
            parsed = json.loads(match.group(0))
        except Exception:
            return []

    if not isinstance(parsed, list) or not parsed:
        return []

    scores = []
    for v in parsed:
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            return []  # not a score array at all
        scores.append(min(max(float(v), 0.0), 10.0))

    # A short/long array means the model lost track of the passages. Keep what
    # it gave positionally rather than discarding the whole judgement; the
    # unscored tail falls back to retrieval evidence in rerank().
    return scores[:expected] if len(scores) >= expected else scores


async def rerank(query: str, candidates: list[dict], top_k: int) -> list[dict]:
    if not candidates:
        return []

    numbered = "\n\n".join(f"[{i}] {c['text'][:500]}" for i, c in enumerate(candidates))
    prompt = (
        f"Query: {query}\n\n"
        f"Passages ({len(candidates)} total - output exactly {len(candidates)} scores):\n{numbered}"
    )

    fallback = _retrieval_only_scores(candidates)
    try:
        raw = await ollama.chat(_RERANK_SYSTEM, prompt, temperature=0.0)
        scores = _parse_scores(raw, len(candidates))
    except Exception:
        scores = []

    # An all-zero array is taken at face value: "none of these passages are
    # relevant". It is sometimes the model being lazy when an answer IS present,
    # but it is also the correct verdict when the project genuinely has nothing
    # on the topic - and the two are indistinguishable from the array alone.
    # Substituting retrieval scores here would report medium confidence on a
    # question the documents cannot answer, which is the exact failure this
    # meter exists to prevent. Under-claiming is the safe direction.
    if len(scores) < len(candidates):
        scores = list(scores) + fallback[len(scores):]

    for c, s in zip(candidates, scores):
        c["rerank_score"] = s

    ranked = sorted(candidates, key=lambda c: c["rerank_score"], reverse=True)
    return ranked[:top_k]
