"""Task API routes for the shared job lifecycle."""

import hashlib
import json
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from pydantic import BaseModel, Field

from mrhub.api.dependencies import require_user
from mrhub.domain.tasks import TaskRecord, TaskStatus
from mrhub.infrastructure.database import TaskRepository
from mrhub.jobs.engine import JobEngine
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


@router.post("", response_model=TaskRecord, status_code=201)
def create_task(
    payload: CreateTaskRequest,
    response: Response,
    user: Annotated[AuthenticatedUser, Depends(require_user)],
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> TaskRecord:
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
            return existing
        saved = repository.get(task.task_id)
        if saved is None:
            raise HTTPException(status_code=500, detail="Task reservation could not be read back")
    else:
        saved = JobEngine(repository).submit(task)

    AuditLogger(repository).record(
        event_type="task.submitted",
        outcome="waiting_approval" if saved.status is TaskStatus.WAITING_APPROVAL else "queued",
        subject_id=str(saved.task_id),
        metadata={
            "task_type": saved.task_type,
            "risk_class": saved.risk_class.value,
            "decision": decision.decision.value,
        },
    )
    return saved


@router.get("/{task_id}", response_model=TaskRecord)
def get_task(task_id: UUID) -> TaskRecord:
    task = get_engine().get(task_id)
    if task is None or task.task_type == "video.scene_detection":
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.get("/{task_id}/result")
def get_task_result(task_id: UUID) -> dict[str, object]:
    repository = get_repository()
    task = repository.get(task_id)
    if task is None or task.task_type == "video.scene_detection":
        raise HTTPException(status_code=404, detail="Task not found")
    result = WorkerEngine(repository).get_result(task_id)
    if result is None:
        raise HTTPException(status_code=409, detail="Task has not been processed yet")
    return result


@router.get("", response_model=list[TaskRecord])
def list_tasks(limit: int = Query(default=50, ge=1, le=100)) -> list[TaskRecord]:
    # Video scene jobs carry a separate owner scope; their status/results are
    # available only through /video-intelligence/scene-jobs/{job_id}.
    tasks = get_repository().list_recent(100)
    visible = [task for task in tasks if task.task_type != "video.scene_detection"]
    return visible[:limit]
