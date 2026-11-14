"""Authenticated API for evidence-backed people-needs research."""
from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from mrhub.api.dependencies import require_user
from mrhub.config import get_settings
from mrhub.research.discovery import ResearchDiscoveryError, discover_public_needs
from mrhub.research.repository import (
    OPPORTUNITY_STATUSES,
    ResearchConflictError,
    ResearchNotFound,
    ResearchRepository,
    ResearchValidationError,
)
from mrhub.security.auth import AuthenticatedUser

router = APIRouter(prefix="/research", tags=["research"], dependencies=[Depends(require_user)])


class OpportunityRequest(BaseModel):
    domain_id: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=160)
    problem_statement: str = Field(min_length=1, max_length=4000)
    audience: str = Field(min_length=1, max_length=240)
    solution_hypothesis: str = Field(default="", max_length=2000)


class EvidenceRequest(BaseModel):
    source_type: Literal[
        "public_discussion", "community_forum", "app_review", "research_report", "support_request", "other"
    ]
    source_url: str = Field(min_length=1, max_length=2048)
    source_label: str = Field(min_length=1, max_length=120)
    observation_summary: str = Field(min_length=1, max_length=2000)
    signal_strength: Literal["low", "medium", "high"] = "medium"
    published_at: str | None = Field(default=None, max_length=40)


class AssessmentRequest(BaseModel):
    status: Literal[
        "new", "validating", "validated", "prioritized", "in_progress", "deferred", "rejected"
    ] | None = None
    impact_score: int | None = Field(default=None, ge=1, le=5)
    frequency_score: int | None = Field(default=None, ge=1, le=5)
    feasibility_score: int | None = Field(default=None, ge=1, le=5)
    solution_hypothesis: str | None = Field(default=None, max_length=2000)


class FeedbackRequest(BaseModel):
    domain_id: str = Field(min_length=1, max_length=80)
    audience_segment: str = Field(min_length=1, max_length=120)
    need_summary: str = Field(min_length=1, max_length=2000)
    current_workaround: str = Field(default="", max_length=1200)
    impact_score: int | None = Field(default=None, ge=1, le=5)
    frequency_score: int | None = Field(default=None, ge=1, le=5)
    consent_to_research: Literal[True]


class FeedbackStatusRequest(BaseModel):
    status: Literal["new", "reviewed", "converted", "dismissed"]


class OutcomeMeasurementRequest(BaseModel):
    metric_name: Literal[
        "task_time_saved_minutes", "task_completion_rate_percent",
        "user_satisfaction_score", "error_rate_percent", "active_users", "operating_cost",
    ]
    baseline_value: float = Field(ge=0, allow_inf_nan=False)
    observed_value: float = Field(ge=0, allow_inf_nan=False)
    unit: str = Field(min_length=1, max_length=40)
    sample_size: int = Field(ge=1, le=1_000_000)
    period_start: str = Field(min_length=1, max_length=40)
    period_end: str = Field(min_length=1, max_length=40)
    notes: str = Field(default="", max_length=1200)


def get_research_repository() -> ResearchRepository:
    return ResearchRepository(get_settings().database_path)


def _opportunity_payload(repository: ResearchRepository, owner_id: str, opportunity_id: str) -> dict[str, object]:
    opportunity = repository.get_opportunity(owner_user_id=owner_id, opportunity_id=opportunity_id)
    return {**opportunity.as_dict(), "evidence": [item.as_dict() for item in repository.list_evidence(
        owner_user_id=owner_id, opportunity_id=opportunity_id
    )]}


@router.post("/opportunities", status_code=status.HTTP_201_CREATED)
def create_opportunity(
    payload: OpportunityRequest,
    user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> dict[str, object]:
    try:
        created = get_research_repository().create_opportunity(
            owner_user_id=user.user_id, **payload.model_dump()
        )
        return {**created.as_dict(), "evidence": []}
    except ResearchValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/opportunities")
def list_opportunities(
    user: Annotated[AuthenticatedUser, Depends(require_user)],
    opportunity_status: Literal[
        "new", "validating", "validated", "prioritized", "in_progress", "deferred", "rejected"
    ] | None = Query(default=None, alias="status"),
    domain_id: str | None = Query(default=None, max_length=80),
    limit: int = Query(default=50, ge=1, le=100),
) -> dict[str, object]:
    try:
        items = get_research_repository().list_opportunities(
            owner_user_id=user.user_id, status=opportunity_status, domain_id=domain_id, limit=limit
        )
    except ResearchValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"items": [item.as_dict() for item in items], "count": len(items), "allowed_statuses": sorted(OPPORTUNITY_STATUSES)}


@router.get("/opportunities/{opportunity_id}")
def get_opportunity(
    opportunity_id: str,
    user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> dict[str, object]:
    try:
        return _opportunity_payload(get_research_repository(), user.user_id, opportunity_id)
    except ResearchNotFound as exc:
        raise HTTPException(status_code=404, detail="Research opportunity not found") from exc


@router.post("/opportunities/{opportunity_id}/evidence", status_code=status.HTTP_201_CREATED)
def add_evidence(
    opportunity_id: str,
    payload: EvidenceRequest,
    user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> dict[str, object]:
    repository = get_research_repository()
    try:
        evidence = repository.add_evidence(
            owner_user_id=user.user_id, opportunity_id=opportunity_id, **payload.model_dump()
        )
        return evidence.as_dict()
    except ResearchNotFound as exc:
        raise HTTPException(status_code=404, detail="Research opportunity not found") from exc
    except ResearchConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ResearchValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.patch("/opportunities/{opportunity_id}")
def update_assessment(
    opportunity_id: str,
    payload: AssessmentRequest,
    user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> dict[str, object]:
    repository = get_research_repository()
    try:
        repository.update_assessment(
            owner_user_id=user.user_id, opportunity_id=opportunity_id, **payload.model_dump()
        )
        return _opportunity_payload(repository, user.user_id, opportunity_id)
    except ResearchNotFound as exc:
        raise HTTPException(status_code=404, detail="Research opportunity not found") from exc
    except ResearchConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ResearchValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/feedback", status_code=status.HTTP_201_CREATED)
def create_feedback(
    payload: FeedbackRequest,
    user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> dict[str, object]:
    """Record consented, minimized user feedback without collecting contact details."""
    try:
        return get_research_repository().create_feedback(
            owner_user_id=user.user_id, **payload.model_dump()
        )
    except ResearchValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/feedback/entries")
def list_feedback(
    user: Annotated[AuthenticatedUser, Depends(require_user)],
    feedback_status: Literal["new", "reviewed", "converted", "dismissed"] | None = Query(
        default=None, alias="status"
    ),
    domain_id: str | None = Query(default=None, max_length=80),
    limit: int = Query(default=50, ge=1, le=100),
) -> dict[str, object]:
    try:
        items = get_research_repository().list_feedback(
            owner_user_id=user.user_id, status=feedback_status, domain_id=domain_id, limit=limit
        )
    except ResearchValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"items": items, "count": len(items)}


@router.patch("/feedback/{feedback_id}")
def update_feedback_status(
    feedback_id: str,
    payload: FeedbackStatusRequest,
    user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> dict[str, object]:
    repository = get_research_repository()
    try:
        return repository.update_feedback_status(
            owner_user_id=user.user_id, feedback_id=feedback_id, status=payload.status
        )
    except ResearchNotFound as exc:
        raise HTTPException(status_code=404, detail="Research feedback not found") from exc
    except ResearchValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.delete("/feedback/{feedback_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_feedback(
    feedback_id: str,
    user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> None:
    deleted = get_research_repository().delete_feedback(
        owner_user_id=user.user_id, feedback_id=feedback_id
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="Research feedback not found")


@router.post("/opportunities/{opportunity_id}/outcomes", status_code=status.HTTP_201_CREATED)
def create_outcome_measurement(
    opportunity_id: str,
    payload: OutcomeMeasurementRequest,
    user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> dict[str, object]:
    try:
        return get_research_repository().create_outcome_measurement(
            owner_user_id=user.user_id, opportunity_id=opportunity_id, **payload.model_dump()
        )
    except ResearchNotFound as exc:
        raise HTTPException(status_code=404, detail="Research opportunity not found") from exc
    except ResearchValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/opportunities/{opportunity_id}/outcomes")
def list_outcome_measurements(
    opportunity_id: str,
    user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> dict[str, object]:
    try:
        items = get_research_repository().list_outcome_measurements(
            owner_user_id=user.user_id, opportunity_id=opportunity_id
        )
    except ResearchNotFound as exc:
        raise HTTPException(status_code=404, detail="Research opportunity not found") from exc
    return {"items": items, "count": len(items)}


@router.get("/discovery/search")
def discover_research_candidates(
    user: Annotated[AuthenticatedUser, Depends(require_user)],
    query: str = Query(min_length=1, max_length=160),
    source: Literal["hacker_news", "stack_exchange"] = "hacker_news",
    site: Literal[
        "stackoverflow", "superuser", "webapps", "askubuntu",
        "serverfault", "workplace", "academia", "writers",
    ] = "superuser",
    limit: int = Query(default=10, ge=1, le=20),
) -> dict[str, object]:
    """Search allow-listed public APIs; results remain review-only candidates."""
    try:
        return discover_public_needs(
            owner_user_id=user.user_id, source=source, query=query,
            database_path=get_settings().database_path, site=site, limit=limit
        )
    except ResearchDiscoveryError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
