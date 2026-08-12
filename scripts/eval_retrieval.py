"""
Retrieval evaluation harness. Proves retrieval quality with numbers instead
of "looked fine in the demo." Run against a small set of known
question -> expected-answer-location pairs after ingesting a real document.

Usage:
    python -m scripts.eval_retrieval --user_id demo --project_id demo \
        --eval_file scripts/eval_set_example.json

eval_set format: list of
    {"question": "...", "expected_keyword": "...", "expected_source_file": "..."}

Metrics reported:
    - Hit@K: was a chunk from the expected source file in the top-K retrieved?
    - Keyword recall: did the expected keyword appear in the retrieved text?
    - Fusion contribution: did vector-only or BM25-only retrieval miss it
      (i.e. did hybrid fusion actually help)?
"""
import argparse
import asyncio
import json
from app.core.llm_client import ollama
from app.core.hybrid_search import hybrid_search, _bm25_search
from app.core.vectorstore import query as vector_query
from app.config import settings


async def run_eval(user_id: str, project_id: str, eval_set: list[dict], top_k: int = 8):
    results = []
    for case in eval_set:
        question = case["question"]
        expected_kw = case.get("expected_keyword", "").lower()
        expected_source = case.get("expected_source_file")

        q_emb = await ollama.embed(question)

        vec_only = vector_query(user_id, project_id, q_emb, top_k)
        bm25_only = _bm25_search(user_id, project_id, question, top_k)
        fused = hybrid_search(user_id, project_id, question, q_emb, top_k)

        def hit(chunks):
            for c in chunks:
                text_ok = expected_kw in c["text"].lower() if expected_kw else True
                source_ok = (c["metadata"].get("source_file") == expected_source) if expected_source else True
                if text_ok and source_ok:
                    return True
            return False

        vec_hit, bm25_hit, fused_hit = hit(vec_only), hit(bm25_only), hit(fused)

        # "fusion rescued" = hybrid found it but at least one individual method missed it
        fusion_rescued = fused_hit and (not vec_hit or not bm25_hit)

        results.append({
            "question": question,
            "vector_only_hit": vec_hit,
            "bm25_only_hit": bm25_hit,
            "hybrid_hit": fused_hit,
            "fusion_rescued": fusion_rescued,
        })

    total = len(results)
    hybrid_hit_rate = sum(r["hybrid_hit"] for r in results) / total if total else 0
    vector_hit_rate = sum(r["vector_only_hit"] for r in results) / total if total else 0
    bm25_hit_rate = sum(r["bm25_only_hit"] for r in results) / total if total else 0

    summary = {
        "total_cases": total,
        "hybrid_hit_rate": round(hybrid_hit_rate, 3),
        "vector_only_hit_rate": round(vector_hit_rate, 3),
        "bm25_only_hit_rate": round(bm25_hit_rate, 3),
        "per_case": results,
    }
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--user_id", required=True)
    parser.add_argument("--project_id", required=True)
    parser.add_argument("--eval_file", required=True)
    parser.add_argument("--top_k", type=int, default=settings.top_k_retrieval)
    args = parser.parse_args()

    with open(args.eval_file) as f:
        eval_set = json.load(f)

    summary = asyncio.run(run_eval(args.user_id, args.project_id, eval_set, args.top_k))

    print(f"\n=== Retrieval Eval: {summary['total_cases']} cases ===")
    print(f"Hybrid hit rate:      {summary['hybrid_hit_rate']*100:.1f}%")
    print(f"Vector-only hit rate: {summary['vector_only_hit_rate']*100:.1f}%")
    print(f"BM25-only hit rate:   {summary['bm25_only_hit_rate']*100:.1f}%\n")
    for r in summary["per_case"]:
        status = "PASS" if r["hybrid_hit"] else "FAIL"
        print(f"[{status}] {r['question']}")


if __name__ == "__main__":
    main()
