"""Job lifecycle API."""

from uuid import UUID

from fastapi import APIRouter, HTTPException

from mrhub.domain.tasks import TaskRecord
from mrhub.infrastructure.database import TaskRepository
from mrhub.jobs.engine import InvalidTaskTransition, JobEngine

router = APIRouter(prefix="/jobs", tags=["jobs"])


def engine() -> JobEngine:
    from mrhub.config import get_settings
    repository = TaskRepository(get_settings().database_path)
    repository.initialize()
    return JobEngine(repository)


@router.post("/{task_id}/cancel", response_model=TaskRecord)
def cancel(task_id: UUID) -> TaskRecord:
    try:
        return engine().cancel(task_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Task not found") from exc
    except (InvalidTaskTransition, RuntimeError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
