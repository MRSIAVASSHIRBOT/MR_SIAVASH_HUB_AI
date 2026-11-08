from client_helpers import authenticated_client


def test_knowledge_retrieval_quality_evaluation_endpoint() -> None:
    """The endpoint returns metrics from a synthetic, local-only corpus."""
    client = authenticated_client()

    response = client.get("/knowledge/evaluation/reference")
    assert response.status_code == 200

    report = response.json()
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
