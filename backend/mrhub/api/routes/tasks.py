"""Task API routes for the shared job lifecycle."""

import base64
import binascii
import hashlib
import json
import re
from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from pydantic import BaseModel, Field

from mrhub.api.dependencies import require_user
from mrhub.domain.tasks import TaskRecord, TaskStatus
from mrhub.infrastructure.database import TaskRepository
from mrhub.jobs.engine import InvalidTaskTransition, JobEngine
from mrhub.jobs.idempotency import (
    IdempotencyConflict,
    IdempotencyError,
    IdempotencyRepository,
)
from mrhub.jobs.worker import WorkerEngine
from mrhub.security.audit import AuditLogger
from mrhub.security.auth import AuthenticatedUser
from mrhub.security.policy import ActionRequest, PolicyDecision, PolicyEngine

router = APIRouter(prefix="/tasks", tags=["tasks"], dependencies=[Depends(require_user)])
policy = PolicyEngine()


class CreateTaskRequest(BaseModel):
    task_type: str = Field(min_length=1, max_length=80, pattern=r"^[a-zA-Z0-9_.-]+$")
    description: str = Field(default="", max_length=500)


def get_repository() -> TaskRepository:
    from mrhub.config import get_settings

    repository = TaskRepository(get_settings().database_path)
    repository.initialize()
    return repository


def get_engine() -> JobEngine:
    return JobEngine(get_repository())



def _encode_task_event_cursor(created_at: str, event_id: str) -> str:
    payload = f"{created_at}\n{event_id}".encode()
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def _decode_task_event_cursor(cursor: str) -> tuple[str, str]:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,512}", cursor):
        raise ValueError("Invalid task history cursor")
    try:
        padding = "=" * (-len(cursor) % 4)
        payload = base64.b64decode(
            cursor + padding, altchars=b"-_", validate=True
        ).decode("utf-8")
        created_at, event_id = payload.split("\n", 1)
        if not created_at or len(created_at) > 64:
            raise ValueError("Invalid task history cursor")
        parsed_at = datetime.fromisoformat(created_at)
        if parsed_at.tzinfo is None or parsed_at.utcoffset() is None:
            raise ValueError("Invalid task history cursor")
        parsed_id = UUID(event_id)
        if str(parsed_id) != event_id:
            raise ValueError("Invalid task history cursor")
    except (binascii.Error, UnicodeDecodeError, ValueError):
        raise ValueError("Invalid task history cursor") from None
    return created_at, event_id


@router.post("", response_model=TaskRecord, status_code=201)
def create_task(
    payload: CreateTaskRequest,
    response: Response,
    user: Annotated[AuthenticatedUser, Depends(require_user)],
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> TaskRecord:
    if payload.task_type == "video.scene_detection":
        raise HTTPException(
            status_code=403,
            detail="Use the dedicated video-intelligence scene-job API",
        )
    risk_class = policy.classify_task_type(payload.task_type)
    decision = policy.evaluate(ActionRequest(
        action="task.submit",
        risk_class=risk_class,
    ))
    if decision.decision is PolicyDecision.DENY:
        raise HTTPException(status_code=403, detail=decision.reason)

    task = TaskRecord(
        task_type=payload.task_type,
        description=payload.description,
        risk_class=risk_class,
        status=(
            TaskStatus.WAITING_APPROVAL
            if decision.decision is PolicyDecision.REQUIRE_APPROVAL
            else TaskStatus.QUEUED
        ),
    )
    repository = get_repository()
    if idempotency_key is not None:
        canonical_request = json.dumps(
            {
                "task_type": task.task_type,
                "description": task.description,
                "risk_class": task.risk_class.value,
                "status": task.status.value,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        request_digest = hashlib.sha256(canonical_request).hexdigest()
        try:
            reservation = IdempotencyRepository(repository.database_path).reserve_task(
                f"user:{user.user_id}", idempotency_key, request_digest, task
            )
        except IdempotencyConflict as exc:
            raise HTTPException(status_code=409, detail="Idempotency key conflict") from exc
        except IdempotencyError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        if not reservation.created:
            if reservation.record.task_id is None:
                raise HTTPException(status_code=409, detail="Idempotency reservation is incomplete")
            existing = repository.get(UUID(reservation.record.task_id))
            if existing is None:
                raise HTTPException(status_code=409, detail="Idempotent task is unavailable")
            response.status_code = 200
            response.headers["X-Trace-ID"] = str(existing.task_id)
            return existing
        saved = repository.get(task.task_id)
        if saved is None:
            raise HTTPException(status_code=500, detail="Task reservation could not be read back")
    else:
        saved = JobEngine(repository).submit(task)

    response.headers["X-Trace-ID"] = str(saved.task_id)
    AuditLogger(repository).record(
        event_type="task.submitted",
        outcome="waiting_approval" if saved.status is TaskStatus.WAITING_APPROVAL else "queued",
        subject_id=str(saved.task_id),
        actor_type="user",
        actor_id=user.user_id,
        metadata={
            "task_type": saved.task_type,
            "risk_class": saved.risk_class.value,
            "decision": decision.decision.value,
            "trace_id": str(saved.task_id),
        },
    )
    return saved


@router.get("/{task_id}/events")
def get_task_history(
    task_id: UUID,
    user: Annotated[AuthenticatedUser, Depends(require_user)],
    limit: int = Query(default=20, ge=1, le=50),
    cursor: str | None = None,
) -> dict[str, object]:
    """Return one bounded, stable history page for the authenticated task owner."""
    before = None
    if cursor is not None:
        try:
            before = _decode_task_event_cursor(cursor)
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid task history cursor") from None
    page = get_repository().list_task_audit_event_page_for_user(
        task_id,
        user.user_id,
        limit,
        before=before,
    )
    if page is None:
        raise HTTPException(status_code=404, detail="Task not found")
    events = page["events"]
    next_cursor = None
    if page["has_more"] and events:
        last = events[-1]
        next_cursor = _encode_task_event_cursor(
            str(last["created_at"]), str(last["event_id"])
        )
    return {
        "task_id": str(task_id),
        "events": events,
        "count": len(events),
        "has_more": page["has_more"],
        "next_cursor": next_cursor,
    }


@router.post("/{task_id}/cancel", response_model=TaskRecord)
def cancel_task(
    task_id: UUID,
    user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> TaskRecord:
    """Cancel only an owned task that has not started executing."""
    repository = get_repository()
    task = repository.get_for_user(user.user_id, task_id)
    if task is None or task.task_type == "video.scene_detection":
        raise HTTPException(status_code=404, detail="Task not found")
    try:
        cancelled = JobEngine(repository).cancel_pending(task_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Task not found") from exc
    except (InvalidTaskTransition, RuntimeError) as exc:
        raise HTTPException(status_code=409, detail="Task is no longer cancellable") from exc
    AuditLogger(repository).record(
        event_type="task.cancelled",
        outcome="success",
        subject_type="task",
        subject_id=str(task_id),
        actor_type="user",
        actor_id=user.user_id,
        metadata={
            "previous_status": task.status.value,
            "new_status": cancelled.status.value,
        },
    )
    return cancelled


@router.get("/{task_id}", response_model=TaskRecord)
def get_task(
    task_id: UUID,
    user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> TaskRecord:
    task = get_repository().get_for_user(user.user_id, task_id)
    if task is None or task.task_type == "video.scene_detection":
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.get("/{task_id}/result")
def get_task_result(
    task_id: UUID,
    user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> dict[str, object]:
    repository = get_repository()
    task = repository.get_for_user(user.user_id, task_id)
    if task is None or task.task_type == "video.scene_detection":
        raise HTTPException(status_code=404, detail="Task not found")
    result = WorkerEngine(repository).get_result(task_id)
    if result is None:
        raise HTTPException(status_code=409, detail="Task has not been processed yet")
    return result


@router.get("", response_model=list[TaskRecord])
def list_tasks(
    user: Annotated[AuthenticatedUser, Depends(require_user)],
    limit: int = Query(default=50, ge=1, le=100),
) -> list[TaskRecord]:
    return get_repository().list_recent_for_user(user.user_id, limit)
