import json
from pathlib import Path

from client_helpers import authenticated_client


def test_synthetic_knowledge_retrieval_corpus_returns_expected_source_at_rank_one() -> None:
    cases = json.loads(Path(__file__).with_name("knowledge_eval.json").read_text(encoding="utf-8"))
    client = authenticated_client()
    for case in cases:
        created = client.post(
            "/knowledge/documents",
            json={"title": case["title"], "content": case["content"]},
        )
        assert created.status_code == 201

    for case in cases:
        response = client.post("/knowledge/search", json={"query": case["query"], "limit": 5})
        assert response.status_code == 200
        results = response.json()["results"]
        assert results, f"No result for evaluation query: {case['query']}"
        assert results[0]["title"] == case["expected_title"], (
            f"Expected {case['expected_title']!r} at rank 1 for {case['query']!r}, "
            f"got {results[0]['title']!r}"
        )
        assert results[0]["citation_ref"].startswith("knowledge://documents/")
        assert results[0]["content_integrity_verified"] is True



def test_reference_retrieval_benchmark_reports_repeatable_quality_metrics():
    from mrhub.knowledge.evaluation import run_reference_evaluation

    report = run_reference_evaluation()

    assert report["benchmark"] == "synthetic_fixture_corpus"
    assert report["cases_evaluated"] == 5
    assert report["fixture_documents"] == 5
    assert report["precision_at_k"] == 1 / 3
    assert report["recall_at_k"] == 1.0
    assert report["mean_reciprocal_rank"] == 1.0
    assert report["hit_rate"] == 1.0
    assert report["retrieved_source_text_included"] is False
    assert report["network_accessed"] is False
    assert report["production_quality_claim"] is False
