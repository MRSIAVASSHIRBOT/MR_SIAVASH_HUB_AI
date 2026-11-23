"""Authenticated policy inspection using server-authoritative action metadata."""

from __future__ import annotations

import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from mrhub.api.dependencies import require_user
from mrhub.config import get_settings
from mrhub.infrastructure.database import TaskRepository
from mrhub.security.audit import AuditLogger
from mrhub.security.auth import AuthenticatedUser
from mrhub.security.policy import (
    ActionRequest,
    PolicyDecision,
    PolicyEngine,
    PolicyResult,
)
from mrhub.security.tool_permissions import ToolPermissionService
from mrhub.tools.builtins import build_tool_registry

router = APIRouter(prefix="/policy", tags=["policy"], dependencies=[Depends(require_user)])
engine = PolicyEngine()


class EvaluatePolicyRequest(BaseModel):
    """An untrusted action name only; all policy facts are server-owned."""

    model_config = ConfigDict(extra="forbid", strict=True)

    action: str = Field(
        min_length=1,
        max_length=80,
        pattern=r"^[a-z][a-z0-9_.-]{0,79}$",
        strict=True,
    )


@router.post("/evaluate", response_model=PolicyResult)
def evaluate_policy(
    payload: EvaluatePolicyRequest,
    user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> PolicyResult:
    """Inspect registered action metadata against the authenticated owner's grants.

    The request cannot supply risk, side-effect, permission, or approval facts.
    Registered tool metadata is authoritative; an unknown action fails closed
    to review-required. This endpoint never invokes a tool or executes an action.
    """
    repository = TaskRepository(get_settings().database_path)
    repository.initialize()
    audit = AuditLogger(repository)
    permission_service = ToolPermissionService(repository, audit)

    try:
        registry = build_tool_registry(owner_user_id=user.user_id)
    except (TypeError, ValueError, RuntimeError) as exc:
        raise HTTPException(
            status_code=503,
            detail="Server action registry is unavailable",
        ) from exc

    try:
        granted_permissions = permission_service.active_permissions(user.user_id)
    except sqlite3.Error as exc:
        raise HTTPException(
            status_code=503,
            detail="Permission grant storage is unavailable",
        ) from exc

    try:
        tool = registry.get(payload.action)
    except LookupError:
        # An unregistered action has no trusted risk/permission definition.
        # It must never be represented as allowed based on caller-supplied facts.
        decision = PolicyResult(
            decision=PolicyDecision.REQUIRE_APPROVAL,
            reason="Unregistered action requires explicit review",
        )
        risk_class = "unknown"
        required_permission_count = 0
    else:
        decision = engine.evaluate(
            ActionRequest(
                action=f"tool.invoke:{tool.name}",
                risk_class=tool.risk_class,
                granted_permissions=granted_permissions,
                required_permissions=tool.required_permissions,
                external_side_effect=tool.external_side_effect,
                user_approved=False,
            )
        )
        risk_class = tool.risk_class.value
        required_permission_count = len(tool.required_permissions)

    try:
        audit.record(
            event_type="policy.evaluated",
            outcome=decision.decision.value,
            subject_type="policy_action",
            subject_id=payload.action,
            actor_type="user",
            actor_id=user.user_id,
            metadata={
                "decision": decision.decision.value,
                "risk_class": risk_class,
                "required_permission_count": required_permission_count,
                "granted_permission_count": (
                    len(granted_permissions)
                ),
            },
        )
    except sqlite3.Error as exc:
        raise HTTPException(
            status_code=503,
            detail="Policy audit storage is unavailable",
        ) from exc
    return decision
