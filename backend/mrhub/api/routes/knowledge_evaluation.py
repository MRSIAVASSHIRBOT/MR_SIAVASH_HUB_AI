"""Authenticated quality evaluation endpoint for knowledge retrieval."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from mrhub.api.dependencies import require_user
from mrhub.knowledge.evaluation import run_reference_evaluation
from mrhub.security.audit import AuditLogger
from mrhub.security.auth import AuthenticatedUser
from mrhub.infrastructure.database import TaskRepository
from mrhub.config import get_settings

router = APIRouter(
    prefix="/knowledge/evaluation",
    tags=["knowledge-evaluation"],
    dependencies=[Depends(require_user)],
)


@router.get("/reference", summary="Run synthetic reference evaluation benchmark")
def run_retrieval_quality_evaluation(
    user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> dict[str, object]:
    """Run the deterministic synthetic evaluation benchmark and return quality metrics.

    This endpoint runs a repeatable benchmark that evaluates the lexical retrieval
    quality of the knowledge base without accessing or modifying any user data.
    The benchmark uses a fixed set of synthetic documents and queries to provide
    consistent, comparable metrics.

    The evaluation measures:
    - Precision@K: proportion of retrieved documents that are relevant
    - Recall@K: proportion of relevant documents that are retrieved
    - Mean Reciprocal Rank (MRR): effectiveness of ranking
    - Hit rate: whether relevant documents are in top-k results

    Returns:
        A report containing quality metrics and benchmark metadata.
    """
    settings = get_settings()
    audit = AuditLogger(TaskRepository(settings.database_path))
    try:
        report = run_reference_evaluation()
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail="Retrieval evaluation benchmark failed"
        ) from exc

    audit.record(
        event_type="knowledge.evaluation_run",
        outcome="success",
        subject_type="knowledge_evaluation",
        subject_id=None,
        actor_type="user",
        actor_id=user.user_id,
        metadata={
            "benchmark": report.get("benchmark", "synthetic_fixture_corpus"),
            "cases_evaluated": report.get("cases_evaluated", 0),
            "fixture_documents": report.get("fixture_documents", 0),
            "precision_at_k": report.get("precision_at_k", 0.0),
            "recall_at_k": report.get("recall_at_k", 0.0),
            "mean_reciprocal_rank": report.get("mean_reciprocal_rank", 0.0),
            "hit_rate": report.get("hit_rate", 0.0),
        },
    )
    return report