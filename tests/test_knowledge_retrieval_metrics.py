from pathlib import Path

import pytest

from mrhub.knowledge.evaluation import (
    MAX_DOCUMENT_ID_CHARS,
    MAX_QUERY_CHARS,
    RetrievalCase,
    evaluate_retrieval,
    run_reference_evaluation,
)


class StubKnowledgeRepository:
    def __init__(self, hits):
        self.hits = hits
        self.calls = []

    def search(self, owner_user_id, query, limit=10):
        self.calls.append((owner_user_id, query, limit))
        return self.hits


def test_retrieval_metrics_deduplicate_chunk_hits_by_document() -> None:
    repository = StubKnowledgeRepository(
        [
            {"document_id": "doc-a", "content": "never returned"},
            {"document_id": "doc-a", "content": "duplicate chunk"},
            {"document_id": "doc-b", "content": "never returned"},
        ]
    )

    report = evaluate_retrieval(
        repository,
        "owner-a",
        [RetrievalCase("  bounded query  ", ("doc-b", "doc-c"))],
        k=2,
    )

    assert report["cases_evaluated"] == 1
    assert report["case_results"][0]["retrieved_document_ids"] == ["doc-a", "doc-b"]
    assert report["precision_at_k"] == 0.5
    assert report["recall_at_k"] == 0.5
    assert report["mean_reciprocal_rank"] == 0.5
    assert report["hit_rate"] == 1.0
    assert repository.calls == [("owner-a", "bounded query", 25)]
    assert "never returned" not in str(report)
    assert report["retrieved_source_text_included"] is False
    assert report["network_accessed"] is False


def test_retrieval_metrics_validate_k_case_count_and_query_bounds() -> None:
    repository = StubKnowledgeRepository([])

    with pytest.raises(ValueError, match="k must be between"):
        evaluate_retrieval(
            repository, "owner-a", [RetrievalCase("query", ("doc",))], k=0
        )
    with pytest.raises(ValueError, match="cases must contain"):
        evaluate_retrieval(repository, "owner-a", [], k=1)
    with pytest.raises(ValueError, match="query must contain"):
        evaluate_retrieval(
            repository,
            "owner-a",
            [RetrievalCase("x" * (MAX_QUERY_CHARS + 1), ("doc",))],
            k=1,
        )


def test_retrieval_metrics_validate_relevance_identifier_bounds() -> None:
    repository = StubKnowledgeRepository([])

    with pytest.raises(ValueError, match="between 1 and"):
        evaluate_retrieval(
            repository,
            "owner-a",
            [RetrievalCase("query", tuple(f"doc-{i}" for i in range(101)))],
            k=1,
        )
    with pytest.raises(ValueError, match="bounded string"):
        evaluate_retrieval(
            repository,
            "owner-a",
            [RetrievalCase("query", ("x" * (MAX_DOCUMENT_ID_CHARS + 1),))],
            k=1,
        )
    with pytest.raises(ValueError, match="duplicates"):
        evaluate_retrieval(
            repository,
            "owner-a",
            [RetrievalCase("query", ("doc-a", "doc-a"))],
            k=1,
        )


def test_reference_evaluation_is_synthetic_and_repeatable() -> None:
    first = run_reference_evaluation()
    second = run_reference_evaluation()

    assert first["benchmark"] == "synthetic_fixture_corpus"
    assert first["production_quality_claim"] is False
    assert first["cases_evaluated"] == 5
    assert first["hit_rate"] == 1.0
    assert first["recall_at_k"] == 1.0
    assert first["mean_reciprocal_rank"] == 1.0
    assert first["precision_at_k"] == second["precision_at_k"]
    assert first["network_accessed"] is False
    assert first["retrieved_source_text_included"] is False
