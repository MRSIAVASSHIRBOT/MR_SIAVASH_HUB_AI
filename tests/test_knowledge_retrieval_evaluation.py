from pathlib import Path

import pytest

from mrhub.knowledge.evaluation import (
    RetrievalCase,
    evaluate_retrieval,
    run_reference_evaluation,
)
from mrhub.infrastructure.database import TaskRepository
from mrhub.knowledge.repository import KnowledgeRepository
from mrhub.security.auth import AuthService


def test_retrieval_evaluation_reports_precision_recall_and_mrr(tmp_path: Path):
    database_path = tmp_path / "knowledge.sqlite3"
    tasks = TaskRepository(database_path)
    tasks.initialize()
    AuthService(tasks).initialize_owner("retrieval-evaluation-test-password")
    owner_record = tasks.get_auth_user("owner")
    assert owner_record is not None
    owner = str(owner_record["user_id"])
    repository = KnowledgeRepository(database_path)
    dns = repository.create_document(
        owner,
        title="DNS",
        content="DNS resolver troubleshooting checks hostname resolution and server settings.",
    )
    python = repository.create_document(
        owner,
        title="Python AST",
        content="Python AST analysis parses source without executing the module.",
    )

    report = evaluate_retrieval(
        repository,
        owner,
        [
            RetrievalCase("DNS resolver", (str(dns["document_id"]),)),
            RetrievalCase("Python AST analysis", (str(python["document_id"]),)),
        ],
        k=1,
    )

    assert report["cases_evaluated"] == 2
    assert report["precision_at_k"] == 1.0
    assert report["recall_at_k"] == 1.0
    assert report["mean_reciprocal_rank"] == 1.0
    assert report["hit_rate"] == 1.0
    assert report["retrieved_source_text_included"] is False
    assert report["network_accessed"] is False


def test_retrieval_evaluation_validates_case_and_k_bounds(tmp_path: Path):
    database_path = tmp_path / "knowledge.sqlite3"
    tasks = TaskRepository(database_path)
    tasks.initialize()
    AuthService(tasks).initialize_owner("retrieval-evaluation-test-password")
    owner_record = tasks.get_auth_user("owner")
    assert owner_record is not None
    owner = str(owner_record["user_id"])
    repository = KnowledgeRepository(database_path)

    with pytest.raises(ValueError, match="k must be between"):
        evaluate_retrieval(repository, owner, [RetrievalCase("query", ("doc",))], k=0)
    with pytest.raises(ValueError, match="cases must contain"):
        evaluate_retrieval(repository, owner, [], k=1)
    with pytest.raises(ValueError, match="needs a query"):
        evaluate_retrieval(repository, owner, [RetrievalCase(" ", ("doc",))], k=1)


def test_reference_evaluation_is_synthetic_and_repeatable():
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
