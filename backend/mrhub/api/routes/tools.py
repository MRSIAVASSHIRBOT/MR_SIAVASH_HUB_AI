"""Authenticated tool catalog, owner permission grants, and invocation API."""

from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from mrhub.api.dependencies import get_task_repository, require_user
from mrhub.infrastructure.database import TaskRepository
from mrhub.security.audit import AuditLogger
from mrhub.security.auth import AuthenticatedUser
from mrhub.security.policy import PolicyDecision
from mrhub.security.tool_permissions import (
    DEFAULT_GRANT_SECONDS,
    MAX_GRANT_SECONDS,
    MIN_GRANT_SECONDS,
    ToolPermissionService,
)
from mrhub.tools.builtins import build_tool_registry
from mrhub.tools.registry import ToolExecutionError, ToolPolicyError

router = APIRouter(prefix="/tools", tags=["tools"])

CurrentUser = Annotated[AuthenticatedUser, Depends(require_user)]
PermissionRepository = Annotated[TaskRepository, Depends(get_task_repository)]


class ToolInvokeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    payload: dict[str, object] = Field(default_factory=dict)


class ToolPermissionGrantRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    expires_in_seconds: int = Field(
        default=DEFAULT_GRANT_SECONDS,
        ge=MIN_GRANT_SECONDS,
        le=MAX_GRANT_SECONDS,
    )


def _permission_service(repository: TaskRepository) -> ToolPermissionService:
    return ToolPermissionService(repository, AuditLogger(repository))


@router.get("", dependencies=[Depends(require_user)])
def list_tools() -> list[dict[str, object]]:
    return build_tool_registry().catalog()


@router.get("/grants")
def list_tool_grants(
    response: Response,
    user: CurrentUser,
    repository: PermissionRepository,
) -> list[dict[str, str]]:
    response.headers["Cache-Control"] = "no-store"
    return _permission_service(repository).list_active(user.user_id)


@router.put("/grants/{permission}")
def grant_tool_permission(
    permission: str,
    request: ToolPermissionGrantRequest,
    response: Response,
    user: AuthenticatedUser = Depends(require_user),
    repository: TaskRepository = Depends(get_task_repository),
) -> dict[str, str]:
    response.headers["Cache-Control"] = "no-store"
    try:
        return _permission_service(repository).grant(
            user.user_id,
            permission,
            request.expires_in_seconds,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Permission grant request is invalid") from exc


@router.delete("/grants/{permission}", status_code=204)
def revoke_tool_permission(
    permission: str,
    response: Response,
    user: AuthenticatedUser = Depends(require_user),
    repository: TaskRepository = Depends(get_task_repository),
) -> Response:
    try:
        revoked = _permission_service(repository).revoke(user.user_id, permission)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Permission grant request is invalid") from exc
    if not revoked:
        raise HTTPException(status_code=404, detail="Permission grant was not found")
    response.headers["Cache-Control"] = "no-store"
    return Response(status_code=204, headers={"Cache-Control": "no-store"})


@router.post("/{tool_name}/invoke")
def invoke_tool(
    tool_name: str,
    request: ToolInvokeRequest,
    response: Response,
    user: AuthenticatedUser = Depends(require_user),
    repository: TaskRepository = Depends(get_task_repository),
) -> dict[str, object]:
    response.headers["Cache-Control"] = "no-store"
    registry = build_tool_registry()
    audit = AuditLogger(repository)
    permissions = _permission_service(repository).active_permissions(user.user_id)
    correlation_id = str(uuid4())

    try:
        result = registry.invoke(
            tool_name,
            request.payload,
            granted_permissions=permissions,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="Tool is not registered") from exc
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail="Tool input validation failed") from exc
    except ToolPolicyError as exc:
        reason_code = (
            "approval_required"
            if exc.decision is PolicyDecision.REQUIRE_APPROVAL
            else "permission_denied"
        )
        audit.record(
            event_type="tool.invocation",
            outcome=exc.decision.value,
            subject_id=tool_name[:80],
            subject_type="tool",
            actor_type="user",
            actor_id=user.user_id,
            metadata={
                "tool_name": tool_name,
                "status": exc.decision.value,
                "reason_code": reason_code,
                "correlation_id": correlation_id,
            },
        )
        status_code = 409 if exc.decision is PolicyDecision.REQUIRE_APPROVAL else 403
        raise HTTPException(
            status_code=status_code,
            detail={
                "decision": exc.decision.value,
                "reason": str(exc),
                "correlation_id": correlation_id,
            },
        ) from exc
    except ToolExecutionError as exc:
        audit.record(
            event_type="tool.invocation",
            outcome="failure",
            subject_id=tool_name[:80],
            subject_type="tool",
            actor_type="user",
            actor_id=user.user_id,
            metadata={
                "tool_name": tool_name,
                "status": "handler_failed",
                "reason_code": "tool_handler_failed",
                "correlation_id": correlation_id,
            },
        )
        raise HTTPException(
            status_code=502,
            detail={"reason": "Tool execution failed", "correlation_id": correlation_id},
        ) from exc

    audit.record(
        event_type="tool.invocation",
        outcome="success",
        subject_id=tool_name[:80],
        subject_type="tool",
        actor_type="user",
        actor_id=user.user_id,
        metadata={
            "tool_name": tool_name,
            "status": "success",
            "reason_code": "tool_completed",
            "correlation_id": correlation_id,
        },
    )
    return {
        "tool": tool_name,
        "result": result,
        "executed": True,
        "correlation_id": correlation_id,
    }
