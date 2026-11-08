"""Authenticated quality evaluation endpoint for knowledge retrieval."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from mrhub.api.dependencies import require_user
from mrhub.config import get_settings
from mrhub.infrastructure.database import TaskRepository
from mrhub.knowledge.evaluation import run_reference_evaluation
from mrhub.security.audit import AuditLogger
from mrhub.security.auth import AuthenticatedUser

router = APIRouter(
    prefix="/knowledge/evaluation",
    tags=["knowledge-evaluation"],
    dependencies=[Depends(require_user)],
)


@router.get("/reference", summary="Run synthetic reference evaluation benchmark")
def run_retrieval_quality_evaluation(
    user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> dict[str, object]:
    """Run a deterministic synthetic benchmark without reading user knowledge."""
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
