"""Task API routes for the shared job lifecycle."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from mrhub.domain.tasks import TaskRecord, TaskStatus
from mrhub.infrastructure.database import TaskRepository
from mrhub.jobs.engine import JobEngine
from mrhub.security.policy import ActionRequest, PolicyDecision, PolicyEngine

router = APIRouter(prefix="/tasks", tags=["tasks"])
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
def create_task(payload: CreateTaskRequest) -> TaskRecord:
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
    return get_engine().submit(task)


@router.get("/{task_id}", response_model=TaskRecord)
def get_task(task_id: UUID) -> TaskRecord:
    task = get_engine().get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.get("", response_model=list[TaskRecord])
def list_tasks(limit: int = Query(default=50, ge=1, le=100)) -> list[TaskRecord]:
    return list(get_repository().list_recent(limit))
