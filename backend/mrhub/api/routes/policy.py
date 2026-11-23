"""Authenticated policy inspection using server-authoritative permission grants."""

from __future__ import annotations

import re
import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator

from mrhub.api.dependencies import require_user
from mrhub.config import get_settings
from mrhub.domain.tasks import RiskClass
from mrhub.infrastructure.database import TaskRepository
from mrhub.security.audit import AuditLogger
from mrhub.security.auth import AuthenticatedUser
from mrhub.security.policy import ActionRequest, PolicyEngine, PolicyResult
from mrhub.security.tool_permissions import ToolPermissionService

router = APIRouter(prefix="/policy", tags=["policy"], dependencies=[Depends(require_user)])
engine = PolicyEngine()

_PERMISSION_PATTERN = r"^[a-z][a-z0-9_.:-]{0,79}$"


class EvaluatePolicyRequest(BaseModel):
    """Only describe the proposed action; grants and approval are server-owned."""

    model_config = ConfigDict(extra="forbid")

    action: str = Field(min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9_.:-]+$")
    risk_class: RiskClass
    required_permissions: list[str] = Field(default_factory=list, max_length=32)
    external_side_effect: bool = Field(default=False, strict=True)

    @field_validator("required_permissions")
    @classmethod
    def validate_required_permissions(cls, permissions: list[str]) -> list[str]:
        for permission in permissions:
            if (
                not isinstance(permission, str)
                or not permission
                or len(permission) > 80
                or not permission.isascii()
                or not re.fullmatch(_PERMISSION_PATTERN, permission)
            ):
                raise ValueError("Permission names must be bounded canonical identifiers")
        if len(permissions) != len(set(permissions)):
            raise ValueError("Required permissions must be unique")
        return permissions


@router.post("/evaluate", response_model=PolicyResult)
def evaluate_policy(
    payload: EvaluatePolicyRequest,
    user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> PolicyResult:
    """Evaluate a proposed action against the authenticated owner's active grants.

    Caller-supplied permission claims and approval decisions are rejected by the
    request schema. The endpoint is an inspection operation and never executes
    the described action.
    """
    repository = TaskRepository(get_settings().database_path)
    repository.initialize()
    audit = AuditLogger(repository)
    permission_service = ToolPermissionService(repository, audit)
    granted_permissions = permission_service.active_permissions(user.user_id)

    decision = engine.evaluate(
        ActionRequest(
            action=payload.action,
            risk_class=payload.risk_class,
            granted_permissions=granted_permissions,
            required_permissions=frozenset(payload.required_permissions),
            external_side_effect=payload.external_side_effect,
            user_approved=False,
        )
    )
    try:
        audit.record(
            event_type="policy.evaluated",
            outcome=decision.decision.value,
            subject_type="policy_action",
            subject_id=payload.action[:80],
            actor_type="user",
            actor_id=user.user_id,
            metadata={
                "decision": decision.decision.value,
                "risk_class": payload.risk_class.value,
                "required_permission_count": len(payload.required_permissions),
                "granted_permission_count": len(granted_permissions),
            },
        )
    except sqlite3.Error as exc:
        raise HTTPException(
            status_code=503,
            detail="Policy audit storage is unavailable",
        ) from exc
    return decision
