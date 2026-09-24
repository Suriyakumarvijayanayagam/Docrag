from app.answer import build_sources, confidence_label, public_sources
from app.reranker import RETRIEVAL_ONLY_CEILING, parse_scores, retrieval_only_scores
from app.retrieval import MAX_RRF
from app.streaming import diagram_request


def test_confidence_keys_off_best_passage():
    assert confidence_label([{"rerank_score": 9}, {"rerank_score": 0}], []) == "high"
    assert confidence_label([{"rerank_score": 5}], []) == "medium"
    assert confidence_label([{"rerank_score": 2}], []) == "low"
    assert confidence_label([], []) == "none"


def test_exact_fact_floors_confidence_at_medium():
    assert confidence_label([{"rerank_score": 1}], [{"label": "Vin max"}]) == "medium"
    assert confidence_label([], [{"label": "Vin max"}]) == "medium"


def test_parse_scores_handles_small_model_output():
    assert parse_scores("[7, 0, 10]", 3) == [7.0, 0.0, 10.0]
    assert parse_scores("```json\n[7, 3]\n```", 2) == [7.0, 3.0]
    assert parse_scores("[12, -3]", 2) == [10.0, 0.0]
    assert parse_scores("[1, 2, 3, 4]", 2) == [1.0, 2.0]
    assert parse_scores("[7]", 3) == [7.0]
    assert parse_scores('["a", "b"]', 2) == []
    assert parse_scores("no idea", 2) == []


def test_retrieval_only_scores_never_reach_high():
    scores = retrieval_only_scores([{"rrf": MAX_RRF}, {"rrf": MAX_RRF / 2}, {"rrf": 0}])

    assert scores[0] == RETRIEVAL_ONLY_CEILING
    assert all(score < 7 for score in scores)


def test_sources_number_passages_then_facts_and_hide_full_text():
    passages = [{"id": 1, "document_id": "d1", "filename": "a.pdf", "page_start": 3, "page_end": 4,
                 "section": "", "content": "x" * 3000, "rerank_score": 8.25}]
    facts = [{"document_id": "d1", "filename": "a.pdf", "page": 2, "locator": "p. 2 table 1 row 3",
              "label": "Vin max", "value": "40 V"}]

    sources = build_sources(passages, facts)
    public = public_sources(sources)

    assert [s["index"] for s in sources] == [1, 2]
    assert sources[0]["location"] == "pp. 3-4"
    assert len(sources[0]["snippet"]) == 2000
    assert sources[1]["exact"] and sources[1]["snippet"] == "Vin max: 40 V"
    assert all("content" not in s for s in public)


def test_diagram_request_prefixes():
    assert diagram_request("diagram: power tree") == "power tree"
    assert diagram_request("/diagram boot sequence") == "boot sequence"
    assert diagram_request("Diagram - thermal path") == "thermal path"
    assert diagram_request("What does the diagram on page 2 show?") is None
    assert diagram_request("diagram:") is None
