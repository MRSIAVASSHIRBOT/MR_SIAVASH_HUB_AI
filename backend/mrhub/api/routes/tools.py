"""Authenticated tool catalog, owner permission grants, and invocation API."""

from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from mrhub.api.dependencies import get_task_repository, require_user
from mrhub.infrastructure.database import TaskRepository
from mrhub.security.audit import AuditLogger
from mrhub.security.auth import AuthenticatedUser
from mrhub.security.policy import PolicyDecision
from mrhub.security.tool_approvals import (
    ToolApprovalError,
    ToolInvocationApprovalStore,
    canonical_tool_payload,
    tool_definition_fingerprint,
)
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
    approval_id: UUID | None = None


class ToolApprovalCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    payload: dict[str, object] = Field(default_factory=dict)
    expires_in_seconds: int = Field(default=300, ge=60, le=900)


class ToolApprovalDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    decision: str = Field(pattern="^(approved|rejected)$")


class ToolPermissionGrantRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    expires_in_seconds: int = Field(
        default=DEFAULT_GRANT_SECONDS,
        ge=MIN_GRANT_SECONDS,
        le=MAX_GRANT_SECONDS,
    )


def _permission_service(repository: TaskRepository) -> ToolPermissionService:
    return ToolPermissionService(repository, AuditLogger(repository))


def _approval_store(repository: TaskRepository) -> ToolInvocationApprovalStore:
    return ToolInvocationApprovalStore(repository)


@router.get("")
def list_tools(user: CurrentUser) -> list[dict[str, object]]:
    return build_tool_registry(owner_user_id=user.user_id).catalog()


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
    user: CurrentUser,
    repository: PermissionRepository,
) -> dict[str, str]:
    response.headers["Cache-Control"] = "no-store"
    try:
        return _permission_service(repository).grant(
            user.user_id,
            permission,
            request.expires_in_seconds,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Permission grant request is invalid", headers={"Cache-Control": "no-store"}) from exc


@router.delete("/grants/{permission}", status_code=204)
def revoke_tool_permission(
    permission: str,
    response: Response,
    user: CurrentUser,
    repository: PermissionRepository,
) -> Response:
    try:
        revoked = _permission_service(repository).revoke(user.user_id, permission)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Permission grant request is invalid") from exc
    if not revoked:
        raise HTTPException(status_code=404, detail="Permission grant was not found", headers={"Cache-Control": "no-store"})
    response.headers["Cache-Control"] = "no-store"
    return Response(status_code=204, headers={"Cache-Control": "no-store"})




@router.post("/{tool_name}/approvals", status_code=201)
def request_tool_approval(
    tool_name: str,
    request: ToolApprovalCreateRequest,
    response: Response,
    user: CurrentUser,
    repository: PermissionRepository,
) -> dict[str, object]:
    """Create a pending approval for one normalized payload and current tool definition."""
    response.headers["Cache-Control"] = "no-store"
    registry = build_tool_registry(owner_user_id=user.user_id)
    audit = AuditLogger(repository)
    permissions = _permission_service(repository).active_permissions(user.user_id)
    try:
        tool = registry.get(tool_name)
        _normalized_payload, payload_digest = canonical_tool_payload(tool, request.payload)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="Tool is not registered") from exc
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail="Tool input validation failed") from exc
    except ToolApprovalError as exc:
        raise HTTPException(status_code=422, detail="Tool action could not be fingerprinted") from exc

    decision = registry.evaluate_policy(tool_name, granted_permissions=permissions)
    if decision.decision is PolicyDecision.DENY:
        raise HTTPException(
            status_code=403,
            detail="The action is prohibited or required owner permissions are missing",
        )
    if decision.decision is not PolicyDecision.REQUIRE_APPROVAL:
        raise HTTPException(status_code=409, detail="This tool action does not require approval")

    fingerprint = tool_definition_fingerprint(tool)
    approval_id = str(uuid4())
    audit_event = audit.build_event(
        event_type="tool.approval_requested",
        outcome="pending",
        subject_id=approval_id,
        subject_type="tool_approval",
        actor_type="user",
        actor_id=user.user_id,
        metadata={
            "tool_name": tool_name,
            "approval_id": approval_id,
            "status": "pending",
            "reason_code": "owner_requested_approval",
        },
    ).model_dump(mode="json")
    try:
        record = _approval_store(repository).create(
            approval_id=approval_id,
            owner_user_id=user.user_id,
            tool_name=tool_name,
            payload_digest=payload_digest,
            tool_fingerprint=fingerprint,
            ttl_seconds=request.expires_in_seconds,
            audit_event=audit_event,
        )
    except ToolApprovalError as exc:
        raise HTTPException(status_code=422, detail="Tool approval request is invalid") from exc

    return {
        "approval_id": record["approval_id"],
        "tool_name": tool_name,
        "status": "pending",
        "payload_digest": payload_digest,
        "tool_fingerprint": fingerprint,
        "created_at": record["created_at"],
        "expires_at": record["expires_at"],
        "owner_review_required": True,
        "execution_started": False,
        "tools_executed": False,
    }


@router.post("/{tool_name}/approvals/{approval_id}/decision")
def decide_tool_approval(
    tool_name: str,
    approval_id: UUID,
    request: ToolApprovalDecisionRequest,
    response: Response,
    user: CurrentUser,
    repository: PermissionRepository,
) -> dict[str, object]:
    """Record an explicit owner decision while the exact registered definition is current."""
    response.headers["Cache-Control"] = "no-store"
    registry = build_tool_registry(owner_user_id=user.user_id)
    try:
        tool = registry.get(tool_name)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="Tool is not registered") from exc

    fingerprint = tool_definition_fingerprint(tool)
    audit_event = AuditLogger(repository).build_event(
        event_type="tool.approval_decided",
        outcome=request.decision,
        subject_id=str(approval_id),
        subject_type="tool_approval",
        actor_type="user",
        actor_id=user.user_id,
        metadata={
            "tool_name": tool_name,
            "approval_id": str(approval_id),
            "status": request.decision,
            "decision": request.decision,
            "reason_code": "owner_decision",
        },
    ).model_dump(mode="json")
    try:
        record = _approval_store(repository).decide(
            str(approval_id),
            owner_user_id=user.user_id,
            tool_name=tool_name,
            tool_fingerprint=fingerprint,
            decision=request.decision,
            audit_event=audit_event,
        )
    except ToolApprovalError as exc:
        raise HTTPException(status_code=409, detail="Tool approval is no longer valid") from exc
    if record is None:
        raise HTTPException(status_code=404, detail="Tool approval not found")
    if record["status"] == "expired":
        raise HTTPException(status_code=409, detail="Tool approval expired or its definition changed")

    return {
        "approval_id": str(approval_id),
        "tool_name": tool_name,
        "status": record["status"],
        "payload_digest": record["payload_digest"],
        "expires_at": record["expires_at"],
        "execution_started": False,
        "tools_executed": False,
    }


@router.post("/{tool_name}/invoke")
def invoke_tool(
    tool_name: str,
    request: ToolInvokeRequest,
    response: Response,
    user: CurrentUser,
    repository: PermissionRepository,
) -> dict[str, object]:
    response.headers["Cache-Control"] = "no-store"
    correlation_id = str(uuid4())
    registry = build_tool_registry(correlation_id=correlation_id, owner_user_id=user.user_id)
    audit = AuditLogger(repository)
    permissions = _permission_service(repository).active_permissions(user.user_id)
    approval_id = str(request.approval_id) if request.approval_id is not None else None

    try:
        tool = registry.get(tool_name)
        _normalized_payload, payload_digest = canonical_tool_payload(tool, request.payload)
        fingerprint = tool_definition_fingerprint(tool)
        policy = registry.evaluate_policy(
            tool_name,
            granted_permissions=permissions,
            user_approved=False,
        )
        user_approved = False
        if policy.decision is PolicyDecision.REQUIRE_APPROVAL:
            if approval_id is None:
                raise ToolPolicyError(policy.decision, policy.reason)
            consumed_event = audit.build_event(
                event_type="tool.approval_consumed",
                outcome="consumed",
                subject_id=approval_id,
                subject_type="tool_approval",
                actor_type="user",
                actor_id=user.user_id,
                metadata={
                    "tool_name": tool_name,
                    "approval_id": approval_id,
                    "status": "consumed",
                    "decision": "consumed",
                    "reason_code": "single_use_receipt_consumed",
                },
            ).model_dump(mode="json")
            consumed = _approval_store(repository).consume(
                approval_id,
                owner_user_id=user.user_id,
                tool_name=tool_name,
                payload_digest=payload_digest,
                tool_fingerprint=fingerprint,
                audit_event=consumed_event,
            )
            if not consumed:
                raise ToolApprovalError(
                    "Approval is missing, expired, already consumed, or bound to another action"
                )
            user_approved = True
        elif approval_id is not None:
            raise ToolApprovalError("This tool action does not accept an approval receipt")

        result = registry.invoke(
            tool_name,
            request.payload,
            granted_permissions=permissions,
            user_approved=user_approved,
        )
    except LookupError as exc:
        audit.record(
            event_type="tool.invocation",
            outcome="failure",
            subject_id=tool_name[:80],
            subject_type="tool",
            actor_type="user",
            actor_id=user.user_id,
            metadata={
                "tool_name": tool_name,
                "status": "not_registered",
                "reason_code": "tool_not_registered",
                "correlation_id": correlation_id,
            },
        )
        raise HTTPException(status_code=404, detail="Tool is not registered", headers={"Cache-Control": "no-store"}) from exc
    except ValidationError as exc:
        audit.record(
            event_type="tool.invocation",
            outcome="failure",
            subject_id=tool_name[:80],
            subject_type="tool",
            actor_type="user",
            actor_id=user.user_id,
            metadata={
                "tool_name": tool_name,
                "status": "invalid_input",
                "reason_code": "tool_input_invalid",
                "correlation_id": correlation_id,
            },
        )
        raise HTTPException(status_code=422, detail="Tool input validation failed", headers={"Cache-Control": "no-store"}) from exc
    except ToolApprovalError as exc:
        audit.record(
            event_type="tool.invocation",
            outcome="approval_required",
            subject_id=tool_name[:80],
            subject_type="tool",
            actor_type="user",
            actor_id=user.user_id,
            metadata={
                "tool_name": tool_name,
                "status": "approval_invalid",
                "approval_id": approval_id,
                "reason_code": "approval_receipt_invalid",
                "correlation_id": correlation_id,
            },
        )
        raise HTTPException(
            status_code=409,
            detail={
                "decision": "require_approval",
                "reason": "A valid owner approval is required for this exact action",
                "correlation_id": correlation_id,
            },
            headers={"Cache-Control": "no-store"},
        ) from exc
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
            headers={"Cache-Control": "no-store"},
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
                "approval_id": approval_id,
                "reason_code": "tool_handler_failed",
                "correlation_id": correlation_id,
            },
        )
        raise HTTPException(
            status_code=502,
            detail={"reason": "Tool execution failed", "correlation_id": correlation_id},
            headers={"Cache-Control": "no-store"},
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
            "approval_id": approval_id,
            "reason_code": "tool_completed",
            "correlation_id": correlation_id,
        },
    )
    return {
        "tool": tool_name,
        "result": result,
        "executed": True,
        "approval_consumed": approval_id is not None,
        "correlation_id": correlation_id,
    }
