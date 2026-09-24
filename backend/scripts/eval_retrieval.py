"""
Retrieval evaluation: hit rates on known question -> expected-location pairs,
so retrieval changes are judged by numbers instead of a demo that looked fine.

Run inside the API container after the documents are indexed into a knowledge base:

    docker compose exec api python -m scripts.eval_retrieval \
        --knowledge_base_id <uuid> --eval_file scripts/eval_set_example.json

eval_set format: list of
    {"question": "...", "expected_keyword": "...", "expected_source_file": "..."}

Metrics:
    - Fused hit: a candidate from hybrid retrieval (before reranking) matches.
    - Reranked hit: a match survives into the top-k passages the model sees.
    - Reranked-away: fused found it, the reranker dropped it - a reranker problem,
      not a retrieval one.
"""
import argparse
import json
import uuid

from app.config import settings
from app.reranker import rerank
from app.retrieval import retrieve

# Retrieval is scoped to a knowledge base plus one chat's attachments; a fresh
# id matches no chat, so only the knowledge base is searched.
NO_CHAT = str(uuid.uuid4())


def _hit(candidates: list[dict], keyword: str, source: str | None) -> bool:
    return any(
        (keyword in candidate["content"].lower() if keyword else True)
        and (candidate["filename"] == source if source else True)
        for candidate in candidates
    )


def run_eval(knowledge_base_id: str, eval_set: list[dict], candidates_k: int, top_k: int) -> dict:
    results = []
    for case in eval_set:
        keyword = case.get("expected_keyword", "").lower()
        source = case.get("expected_source_file")
        fused = retrieve(case["question"], knowledge_base_id, NO_CHAT, limit=candidates_k)
        fused_hit = _hit(fused, keyword, source)
        reranked_hit = _hit(rerank(case["question"], [dict(c) for c in fused], top_k), keyword, source)
        results.append({
            "question": case["question"],
            "fused_hit": fused_hit,
            "reranked_hit": reranked_hit,
            "reranked_away": fused_hit and not reranked_hit,
        })
    total = len(results) or 1
    return {
        "total_cases": len(results),
        "fused_hit_rate": round(sum(r["fused_hit"] for r in results) / total, 3),
        "reranked_hit_rate": round(sum(r["reranked_hit"] for r in results) / total, 3),
        "per_case": results,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--knowledge_base_id", required=True)
    parser.add_argument("--eval_file", required=True)
    parser.add_argument("--candidates", type=int, default=settings.retrieval_candidates)
    parser.add_argument("--top_k", type=int, default=settings.retrieval_top_k)
    args = parser.parse_args()

    with open(args.eval_file) as handle:
        eval_set = json.load(handle)
    summary = run_eval(args.knowledge_base_id, eval_set, args.candidates, args.top_k)

    print(f"\n=== Retrieval eval: {summary['total_cases']} cases ===")
    print(f"Fused hit rate (top {args.candidates}):    {summary['fused_hit_rate'] * 100:.1f}%")
    print(f"Reranked hit rate (top {args.top_k}):  {summary['reranked_hit_rate'] * 100:.1f}%\n")
    for result in summary["per_case"]:
        status = "PASS" if result["reranked_hit"] else ("RERANKED AWAY" if result["reranked_away"] else "FAIL")
        print(f"[{status}] {result['question']}")


if __name__ == "__main__":
    main()
