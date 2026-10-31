"""Owner-only, action-bound approval decisions for pending tasks."""

import hashlib
import json
from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from mrhub.api.dependencies import require_user
from mrhub.domain.tasks import TaskStatus
from mrhub.infrastructure.database import TaskRepository
from mrhub.security.audit import AuditLogger
from mrhub.security.auth import AuthenticatedUser

router = APIRouter(
    prefix="/tasks",
    tags=["approvals"],
    dependencies=[Depends(require_user)],
)


class ApprovalRequest(BaseModel):
    decision: Literal["approved", "rejected"]
    reason: str = Field(default="", max_length=500)


class ApprovalResponse(BaseModel):
    approval_id: str
    task_id: UUID
    decision: Literal["approved", "rejected"]
    approver_id: str
    action_fingerprint: str
    reason: str
    created_at: datetime


def get_repository() -> TaskRepository:
    from mrhub.config import get_settings

    repository = TaskRepository(get_settings().database_path)
    repository.initialize()
    return repository


def fingerprint_action(task) -> str:
    """Bind a decision to the exact task intent, excluding mutable lifecycle fields."""
    canonical = json.dumps(
        {
            "task_id": str(task.task_id),
            "task_type": task.task_type,
            "risk_class": task.risk_class.value,
            "description": task.description,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@router.post("/{task_id}/approval", response_model=ApprovalResponse, status_code=201)
def decide_approval(
    task_id: UUID,
    payload: ApprovalRequest,
    user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> ApprovalResponse:
    repository = get_repository()
    task = repository.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.status is not TaskStatus.WAITING_APPROVAL:
        raise HTTPException(status_code=409, detail="Task is not awaiting approval")
    if repository.get_task_approval(task_id) is not None:
        raise HTTPException(status_code=409, detail="A decision already exists for this task")

    now = datetime.now(UTC)
    approval = {
        "approval_id": str(uuid4()),
        "task_id": str(task_id),
        "decision": payload.decision,
        "approver_id": user.user_id,
        "action_fingerprint": fingerprint_action(task),
        "reason": payload.reason,
        "created_at": now.isoformat(),
    }
    target = TaskStatus.QUEUED if payload.decision == "approved" else TaskStatus.REJECTED
    try:
        repository.record_task_approval(
            approval,
            expected_status=TaskStatus.WAITING_APPROVAL,
            target_status=target,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    AuditLogger(repository).record(
        event_type="task.approval_decided",
        outcome=payload.decision,
        subject_id=str(task_id),
        metadata={
            "task_type": task.task_type,
            "risk_class": task.risk_class.value,
            "decision": payload.decision,
            "reason_code": "owner_decision",
            "previous_status": TaskStatus.WAITING_APPROVAL.value,
            "new_status": target.value,
        },
    )
    return ApprovalResponse(
        approval_id=approval["approval_id"],
        task_id=task_id,
        decision=payload.decision,
        approver_id=user.user_id,
        action_fingerprint=approval["action_fingerprint"],
        reason=payload.reason,
        created_at=now,
    )


@router.get("/{task_id}/approval", response_model=ApprovalResponse)
def get_approval(task_id: UUID) -> ApprovalResponse:
    record = get_repository().get_task_approval(task_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Approval not found")
    return ApprovalResponse(
        approval_id=record["approval_id"],
        task_id=task_id,
        decision=record["decision"],
        approver_id=record["approver_id"],
        action_fingerprint=record["action_fingerprint"],
        reason=record["reason"],
        created_at=record["created_at"],
    )
