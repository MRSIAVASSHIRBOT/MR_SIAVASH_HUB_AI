import json

from client_helpers import authenticated_client


def test_knowledge_retrieval_quality_evaluation_endpoint() -> None:
    """Test that the evaluation API endpoint returns valid quality metrics."""
    client = authenticated_client()

    response = client.get("/knowledge/evaluation/reference")
    assert response.status_code == 200

    report = response.json()
    assert "benchmark" in report
    assert report["benchmark"] == "synthetic_fixture_corpus"
    assert "cases_evaluated" in report
    assert report["cases_evaluated"] == 5
    assert "fixture_documents" in report
    assert report["fixture_documents"] == 5
    assert "precision_at_k" in report
    assert report["precision_at_k"] == 1 / 3
    assert "recall_at_k" in report
    assert report["recall_at_k"] == 1.0
    assert "mean_reciprocal_rank" in report
    assert report["mean_reciprocal_rank"] == 1.0
    assert "hit_rate" in report
    assert report["hit_rate"] == 1.0
    assert "retrieved_source_text_included" in report
    assert report["retrieved_source_text_included"] is False
    assert "network_accessed" in report
    assert report["network_accessed"] is False
    assert "production_quality_claim" in report
    assert report["production_quality_claim"] is False
