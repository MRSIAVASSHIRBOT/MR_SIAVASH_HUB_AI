"""Authenticated API for evidence-backed people-needs research."""
from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from mrhub.api.dependencies import require_user
from mrhub.config import get_settings
from mrhub.research.repository import (
    OPPORTUNITY_STATUSES,
    ResearchConflictError,
    ResearchNotFound,
    ResearchRepository,
    ResearchValidationError,
)
from mrhub.security.auth import AuthenticatedUser

router = APIRouter(prefix="/research/opportunities", tags=["research"], dependencies=[Depends(require_user)])


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


def get_research_repository() -> ResearchRepository:
    return ResearchRepository(get_settings().database_path)


def _opportunity_payload(repository: ResearchRepository, owner_id: str, opportunity_id: str) -> dict[str, object]:
    opportunity = repository.get_opportunity(owner_user_id=owner_id, opportunity_id=opportunity_id)
    return {**opportunity.as_dict(), "evidence": [item.as_dict() for item in repository.list_evidence(
        owner_user_id=owner_id, opportunity_id=opportunity_id
    )]}


@router.post("", status_code=status.HTTP_201_CREATED)
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


@router.get("")
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


@router.get("/{opportunity_id}")
def get_opportunity(
    opportunity_id: str,
    user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> dict[str, object]:
    try:
        return _opportunity_payload(get_research_repository(), user.user_id, opportunity_id)
    except ResearchNotFound as exc:
        raise HTTPException(status_code=404, detail="Research opportunity not found") from exc


@router.post("/{opportunity_id}/evidence", status_code=status.HTTP_201_CREATED)
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


@router.patch("/{opportunity_id}")
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
