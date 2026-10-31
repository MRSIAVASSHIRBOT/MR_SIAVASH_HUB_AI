"""Task API routes for the initial control-plane slice."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from mrhub.domain.tasks import RiskClass, TaskRecord
from mrhub.infrastructure.database import TaskRepository

router = APIRouter(prefix="/tasks", tags=["tasks"])


class CreateTaskRequest(BaseModel):
    task_type: str = Field(min_length=1, max_length=80, pattern=r"^[a-zA-Z0-9_.-]+$")
    description: str = Field(default="", max_length=500)
    risk_class: RiskClass = RiskClass.LOW


def get_repository() -> TaskRepository:
    from mrhub.config import get_settings

    settings = get_settings()
    repository = TaskRepository(settings.database_path)
    repository.initialize()
    return repository


@router.post("", response_model=TaskRecord, status_code=201)
def create_task(payload: CreateTaskRequest) -> TaskRecord:
    # This endpoint records a task request; it does not execute model output or tools.
    task = TaskRecord(
        task_type=payload.task_type,
        description=payload.description,
        risk_class=payload.risk_class,
    )
    return get_repository().create(task)


@router.get("/{task_id}", response_model=TaskRecord)
def get_task(task_id: UUID) -> TaskRecord:
    task = get_repository().get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.get("", response_model=list[TaskRecord])
def list_tasks(limit: int = Query(default=50, ge=1, le=100)) -> list[TaskRecord]:
    return list(get_repository().list_recent(limit))
