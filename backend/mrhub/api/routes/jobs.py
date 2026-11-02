"""Job lifecycle API."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from mrhub.api.dependencies import require_user
from mrhub.domain.tasks import TaskRecord
from mrhub.infrastructure.database import TaskRepository
from mrhub.jobs.engine import InvalidTaskTransition, JobEngine
from mrhub.jobs.worker import WorkerEngine
from mrhub.jobs.worker_control import WorkerControlRepository
from mrhub.security.auth import AuthenticatedUser
from typing import Annotated

router = APIRouter(prefix="/jobs", tags=["jobs"], dependencies=[Depends(require_user)])


def engine() -> JobEngine:
    from mrhub.config import get_settings
    repository = TaskRepository(get_settings().database_path)
    repository.initialize()
    return JobEngine(repository)


@router.get("/summary")
def summary() -> dict[str, object]:
    """Return task queue counts and worker mode without starting the worker."""
    from mrhub.config import get_settings

    repository = TaskRepository(get_settings().database_path)
    repository.initialize()
    return WorkerEngine(repository).summary()


@router.post("/{task_id}/cancel", response_model=TaskRecord)
def cancel(task_id: UUID) -> TaskRecord:
    try:
        return engine().cancel(task_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Task not found") from exc
    except (InvalidTaskTransition, RuntimeError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


class EmergencyStopRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


def control_repository() -> tuple[TaskRepository, WorkerControlRepository]:
    from mrhub.config import get_settings

    repository = TaskRepository(get_settings().database_path)
    repository.initialize()
    return repository, WorkerControlRepository(repository.database_path)


@router.get("/control")
def worker_control_status() -> dict[str, object]:
    """Read the durable worker dispatch stop state without starting execution."""
    _repository, control = control_repository()
    return control.get()


@router.post("/emergency-stop")
def enable_emergency_stop(
    payload: EmergencyStopRequest,
    current_user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> dict[str, object]:
    """Block new task claims and schedule dispatch until the owner explicitly resumes."""
    _repository, control = control_repository()
    return control.set_stopped(
        True,
        reason=payload.reason.strip()[:500],
        changed_by=current_user.user_id,
    )


@router.post("/resume")
def resume_worker_dispatch(
    current_user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> dict[str, object]:
    """Explicitly clear the durable stop switch; queued tasks remain queued."""
    _repository, control = control_repository()
    return control.set_stopped(False, reason=None, changed_by=current_user.user_id)
