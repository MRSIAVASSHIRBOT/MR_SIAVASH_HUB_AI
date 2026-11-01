"""Job lifecycle orchestration; this layer records state and never executes shell commands."""

from datetime import UTC, datetime
from typing import ClassVar
from uuid import UUID

from mrhub.domain.tasks import TaskRecord, TaskStatus
from mrhub.infrastructure.database import TaskRepository
from mrhub.jobs.leases import WorkerLease
from mrhub.security.audit import AuditLogger


class InvalidTaskTransition(ValueError):
    """Raised when a task state transition is not allowed."""


class JobEngine:
    ALLOWED: ClassVar[dict[TaskStatus, set[TaskStatus]]] = {
        TaskStatus.QUEUED: {TaskStatus.RUNNING, TaskStatus.CANCELLED},
        TaskStatus.RUNNING: {
            TaskStatus.WAITING_APPROVAL, TaskStatus.SUCCEEDED,
            TaskStatus.FAILED, TaskStatus.CANCELLED,
        },
        TaskStatus.WAITING_APPROVAL: {
            TaskStatus.QUEUED, TaskStatus.CANCELLED, TaskStatus.REJECTED,
        },
        TaskStatus.SUCCEEDED: set(),
        TaskStatus.FAILED: set(),
        TaskStatus.CANCELLED: set(),
        TaskStatus.REJECTED: set(),
    }

    def __init__(self, repository: TaskRepository) -> None:
        self.repository = repository

    def submit(self, task: TaskRecord) -> TaskRecord:
        return self.repository.create(task)

    def get(self, task_id: UUID) -> TaskRecord | None:
        return self.repository.get(task_id)

    def transition(
        self, task_id: UUID, target: TaskStatus, *, lease: WorkerLease | None = None
    ) -> TaskRecord:
        current = self.repository.get(task_id)
        if current is None:
            raise KeyError("Task not found")
        if target not in self.ALLOWED[current.status]:
            raise InvalidTaskTransition(f"Cannot transition {current.status} -> {target}")
        updated = current.model_copy(update={
            "status": target,
            "updated_at": datetime.now(UTC),
        })
        if lease is None:
            saved = self.repository.update_status(task_id, current.status, updated)
        else:
            if lease.task_id != str(task_id):
                raise RuntimeError("Worker lease does not belong to this task")
            saved = self.repository.update_status(
                task_id,
                current.status,
                updated,
                lease_owner=lease.owner,
                fencing_token=lease.fencing_token,
                lease_now=updated.updated_at.isoformat(),
            )
        AuditLogger(self.repository).record(
            event_type="task.status_changed",
            outcome="success",
            subject_id=str(task_id),
            metadata={
                "task_type": current.task_type,
                "previous_status": current.status.value,
                "new_status": target.value,
                "risk_class": current.risk_class.value,
            },
        )
        return saved

    def cancel(self, task_id: UUID) -> TaskRecord:
        """Coordinate workflow cancellation without claiming an external effect was undone."""
        current = self.repository.get(task_id)
        if current is None:
            raise KeyError("Task not found")
        if current.task_type == "agent.workflow":
            from mrhub.jobs.recovery import WorkflowRecoveryRepository

            recovery = WorkflowRecoveryRepository(self.repository.database_path)
            with self.repository._connection() as connection:
                run = connection.execute(
                    "SELECT workflow_id, status FROM workflow_runs WHERE task_id = ?",
                    (str(task_id),),
                ).fetchone()
            if run is not None and run["status"] == "queued" and current.status is TaskStatus.QUEUED:
                recovery.cancel_queued_run(UUID(run["workflow_id"]))
                saved = self.repository.get(task_id)
                if saved is None:
                    raise KeyError("Task not found")
                AuditLogger(self.repository).record(
                    event_type="task.status_changed",
                    outcome="success",
                    subject_id=str(task_id),
                    metadata={
                        "task_type": current.task_type,
                        "previous_status": current.status.value,
                        "new_status": TaskStatus.CANCELLED.value,
                        "risk_class": current.risk_class.value,
                    },
                )
                return saved
            if run is not None and run["status"] == "running" and current.status is TaskStatus.RUNNING:
                # WAITING_APPROVAL is a durable cancellation request. The worker decides
                # cancelled vs recovery_required and commits both records together.
                return self.transition(task_id, TaskStatus.WAITING_APPROVAL)
            if run is not None and run["status"] == "paused" and current.status is TaskStatus.WAITING_APPROVAL:
                recovery.cancel_paused_run(UUID(run["workflow_id"]))
                saved = self.repository.get(task_id)
                if saved is None:
                    raise KeyError("Task not found")
                return saved
            if run is not None and run["status"] == "recovery_required":
                # Do not hide an ambiguous external outcome behind a cancellation label.
                return current
        return self.transition(task_id, TaskStatus.CANCELLED)
