"""Authenticated API for registering and reviewing capability sources."""
from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from mrhub.api.dependencies import require_user
from mrhub.capabilities.registry import (
    STATUSES,
    CapabilityNotFound,
    CapabilityRegistry,
    CapabilityValidationError,
)
from mrhub.config import get_settings
from mrhub.security.auth import AuthenticatedUser

router = APIRouter(
    prefix="/capabilities",
    tags=["capabilities"],
    dependencies=[Depends(require_user)],
)


class CapabilityCandidateRequest(BaseModel):
    source_url: str = Field(min_length=1, max_length=2048)
    display_name: str = Field(min_length=1, max_length=160)
    summary: str = Field(default="", max_length=1000)
    source_kind: Literal[
        "github_repository", "documentation", "package", "api", "other"
    ] = "github_repository"
    integration_type: Literal[
        "connector", "skill", "python_package", "http_api", "adapter", "manual"
    ] = "manual"
    capabilities: list[str] = Field(default_factory=list, max_length=50)
    license_id: str = Field(default="unknown", min_length=1, max_length=80)


class CapabilityTransitionRequest(BaseModel):
    status: Literal["discovered", "reviewing", "approved", "rejected", "disabled"]
    license_id: str | None = Field(default=None, max_length=80)
    evidence: dict[str, str] = Field(default_factory=dict)


def get_registry() -> CapabilityRegistry:
    return CapabilityRegistry(get_settings().database_path)


@router.post("/candidates", status_code=status.HTTP_201_CREATED)
def register_candidate(
    payload: CapabilityCandidateRequest,
    _user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> dict[str, object]:
    """Register a source for review; this endpoint never fetches or executes it."""
    try:
        candidate = get_registry().add_candidate(**payload.model_dump())
    except CapabilityValidationError as exc:
        code = 409 if "already in the catalog" in str(exc) else 422
        raise HTTPException(status_code=code, detail=str(exc)) from exc
    return candidate.as_dict()


@router.get("/candidates")
def list_candidates(
    _user: Annotated[AuthenticatedUser, Depends(require_user)],
    candidate_status: Literal[
        "discovered", "reviewing", "approved", "rejected", "disabled"
    ] | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=100),
) -> dict[str, object]:
    items = get_registry().list_candidates(status=candidate_status, limit=limit)
    return {
        "items": [item.as_dict() for item in items],
        "count": len(items),
        "allowed_statuses": sorted(STATUSES),
    }


@router.get("/candidates/{candidate_id}")
def get_candidate(
    candidate_id: str,
    _user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> dict[str, object]:
    try:
        return get_registry().get(candidate_id).as_dict()
    except CapabilityNotFound as exc:
        raise HTTPException(status_code=404, detail="Capability candidate not found") from exc


@router.post("/candidates/{candidate_id}/transition")
def transition_candidate(
    candidate_id: str,
    payload: CapabilityTransitionRequest,
    _user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> dict[str, object]:
    try:
        candidate = get_registry().transition(
            candidate_id,
            payload.status,
            license_id=payload.license_id,
            evidence=payload.evidence,
        )
    except CapabilityNotFound as exc:
        raise HTTPException(status_code=404, detail="Capability candidate not found") from exc
    except CapabilityValidationError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return candidate.as_dict()
