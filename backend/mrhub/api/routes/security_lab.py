"""Authenticated offline defensive review endpoints; no active scanning or installation."""

from __future__ import annotations

from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from mrhub.api.dependencies import require_user
from mrhub.config import get_settings
from mrhub.infrastructure.database import TaskRepository
from mrhub.security.audit import AuditLogger
from mrhub.security.auth import AuthenticatedUser
from mrhub.security.defensive_lab import (
    DefensiveReviewScope,
    ScopeValidationError,
    audit_configuration_text,
    audit_requirements_text,
    audit_structured_log_text,
)

router = APIRouter(
    prefix="/security-lab",
    tags=["security-lab"],
    dependencies=[Depends(require_user)],
)


class OfflineReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scope: DefensiveReviewScope
    asset: str = Field(min_length=1, max_length=200)
    filename: str = Field(default="config", min_length=1, max_length=255)
    text: str = Field(max_length=1_000_000)


def _audit_review(
    *,
    current_user: AuthenticatedUser,
    event_type: str,
    reason_code: str,
    outcome: str = "success",
) -> None:
    repository = TaskRepository(get_settings().database_path)
    repository.initialize()
    AuditLogger(repository).record(
        event_type=event_type,
        outcome=outcome,
        subject_type="security_review",
        subject_id=str(uuid4()),
        actor_type="user",
        actor_id=current_user.user_id,
        metadata={
            "reason_code": reason_code,
            "decision": "allow" if outcome == "success" else "deny",
            "status": "completed" if outcome == "success" else "denied",
        },
    )


def _run_review(
    request: OfflineReviewRequest,
    current_user: AuthenticatedUser,
    *,
    dependency: bool,
) -> dict[str, object]:
    review_filename = request.filename
    if dependency and review_filename == "config":
        review_filename = "requirements.txt"
    try:
        if dependency:
            result = audit_requirements_text(
                request.text,
                scope=request.scope,
                asset=request.asset,
                filename=review_filename,
            )
            reason_code = "offline_dependency_manifest_review"
        else:
            result = audit_configuration_text(
                request.text,
                scope=request.scope,
                asset=request.asset,
                filename=request.filename,
            )
            reason_code = "offline_configuration_review"
    except ScopeValidationError as exc:
        _audit_review(
            current_user=current_user,
            event_type="security_lab.review_denied",
            reason_code="authorization_scope_denied",
            outcome="denied",
        )
        raise HTTPException(
            status_code=403,
            detail={"reason_code": "authorization_scope_denied"},
        ) from exc
    except ValueError as exc:
        reason = str(exc)
        status_code = 413 if "1 MB" in reason else 422
        raise HTTPException(
            status_code=status_code,
            detail={"reason_code": "review_input_rejected"},
        ) from exc

    _audit_review(
        current_user=current_user,
        event_type="security_lab.review_completed",
        reason_code=reason_code,
    )
    return result


@router.post("/config-review")
def review_configuration(
    request: OfflineReviewRequest,
    current_user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> dict[str, object]:
    """Review supplied configuration text for one explicitly authorized asset."""
    return _run_review(request, current_user, dependency=False)


@router.post("/dependency-review")
def review_dependency_manifest(
    request: OfflineReviewRequest,
    current_user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> dict[str, object]:
    """Review a requirements-style manifest without contacting or installing packages."""
    return _run_review(request, current_user, dependency=True)


@router.post("/log-review")
def review_structured_security_log(
    request: OfflineReviewRequest,
    current_user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> dict[str, object]:
    """Review caller-supplied normalized JSONL security events without network or mutation."""
    try:
        result = audit_structured_log_text(
            request.text,
            scope=request.scope,
            asset=request.asset,
            filename=request.filename if request.filename != "config" else "security-events.jsonl",
        )
    except ScopeValidationError as exc:
        _audit_review(
            current_user=current_user,
            event_type="security_lab.review_denied",
            reason_code="authorization_scope_denied",
            outcome="denied",
        )
        raise HTTPException(
            status_code=403,
            detail={"reason_code": "authorization_scope_denied"},
        ) from exc
    except ValueError as exc:
        reason = str(exc)
        status_code = 413 if "limit" in reason or "10000-line" in reason else 422
        raise HTTPException(
            status_code=status_code,
            detail={"reason_code": "review_input_rejected"},
        ) from exc

    _audit_review(
        current_user=current_user,
        event_type="security_lab.review_completed",
        reason_code="offline_structured_security_log_review",
    )
    return result
