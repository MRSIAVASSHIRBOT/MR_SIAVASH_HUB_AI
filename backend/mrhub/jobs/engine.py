"""Job lifecycle orchestration; this layer records state and never executes shell commands."""

from datetime import datetime, timezone
from uuid import UUID

from mrhub.domain.tasks import TaskRecord, TaskStatus
from mrhub.infrastructure.database import TaskRepository


class InvalidTaskTransition(ValueError):
    """Raised when a task state transition is not allowed."""


class JobEngine:
    ALLOWED = {
        TaskStatus.QUEUED: {TaskStatus.RUNNING, TaskStatus.CANCELLED},
        TaskStatus.RUNNING: {
            TaskStatus.WAITING_APPROVAL, TaskStatus.SUCCEEDED,
            TaskStatus.FAILED, TaskStatus.CANCELLED,
        },
        TaskStatus.WAITING_APPROVAL: {TaskStatus.QUEUED, TaskStatus.CANCELLED},
        TaskStatus.SUCCEEDED: set(),
        TaskStatus.FAILED: set(),
        TaskStatus.CANCELLED: set(),
    }

    def __init__(self, repository: TaskRepository) -> None:
        self.repository = repository

    def submit(self, task: TaskRecord) -> TaskRecord:
        return self.repository.create(task)

    def get(self, task_id: UUID) -> TaskRecord | None:
        return self.repository.get(task_id)

    def transition(self, task_id: UUID, target: TaskStatus) -> TaskRecord:
        current = self.repository.get(task_id)
        if current is None:
            raise KeyError("Task not found")
        if target not in self.ALLOWED[current.status]:
            raise InvalidTaskTransition(f"Cannot transition {current.status} -> {target}")
        updated = current.model_copy(update={
            "status": target,
            "updated_at": datetime.now(timezone.utc),
        })
        return self.repository.update_status(task_id, current.status, updated)

    def cancel(self, task_id: UUID) -> TaskRecord:
        return self.transition(task_id, TaskStatus.CANCELLED)
