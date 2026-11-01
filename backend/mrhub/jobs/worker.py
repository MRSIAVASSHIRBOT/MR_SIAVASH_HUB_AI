"""Bounded, fail-closed worker for explicitly registered safe task handlers.

The worker is deliberately pull-driven: callers invoke run_once(); application startup
never begins executing queued work implicitly. No shell, network, arbitrary code, or
external side effects are available to handlers.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from threading import Event, Lock, Thread
from uuid import UUID, uuid4

from mrhub.domain.tasks import RiskClass, TaskRecord, TaskStatus
from mrhub.infrastructure.database import TaskRepository
from mrhub.jobs.leases import LeaseManager, WorkerLease
from mrhub.security.audit import AuditLogger


class WorkerError(RuntimeError):
    """Raised when a worker cannot safely claim or process a task."""


class RetryableWorkerError(WorkerError):
    """A handler may raise this only for a known transient, safe-to-retry condition."""


def action_fingerprint(task: TaskRecord) -> str:
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


class WorkerEngine:
    """Executes only allow-listed deterministic handlers with bounded concurrency."""

    MAX_CONCURRENCY = 1
    STALE_AFTER_SECONDS = 300
    MAX_ATTEMPTS = 3
    RETRY_BASE_SECONDS = 5
    RETRY_MAX_SECONDS = 60
    RETRY_SAFE_TASK_TYPES = frozenset({"demo.echo"})

    def __init__(
        self,
        repository: TaskRepository,
        clock: Callable[[], datetime] | None = None,
        lease_seconds: int = 60,
    ) -> None:
        self.repository = repository
        self.database_path = repository.database_path
        self._run_lock = Lock()
        self._clock = clock or (lambda: datetime.now(UTC))
        self._worker_id = str(uuid4())
        self._lease_seconds = lease_seconds
        self._lease_manager = LeaseManager(
            self.database_path, lease_seconds=lease_seconds, clock=self._clock
        )
        self.handlers: dict[str, Callable[..., dict[str, object]]] = {
            "demo.echo": self._echo,
        }
        self.handlers["agent.workflow"] = self._run_agent_workflow
        self._initialize()

    def _now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None:
            raise WorkerError("Worker clock must return a timezone-aware datetime")
        return value.astimezone(UTC)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialize(self) -> None:
        """Delegate all persistent schema creation and upgrades to versioned migrations."""
        self.repository.initialize()

    @staticmethod
    def _echo(task: TaskRecord) -> dict[str, object]:
        return {"message": task.description, "task_type": task.task_type}

    def _run_agent_workflow(
        self, task: TaskRecord, lease: WorkerLease, lease_lost: Event
    ) -> dict[str, object]:
        """Dispatch a workflow using the worker's canonical lease."""
        from mrhub.jobs.workflow_dispatch import WorkflowWorkerHandler

        return WorkflowWorkerHandler(self.repository)(
            task, lease=lease, lease_lost=lease_lost
        )

    def _recover_interrupted(self) -> None:
        """Recover stale jobs without replaying an ambiguous workflow step."""
        cutoff = (self._now() - timedelta(seconds=self.STALE_AFTER_SECONDS)).isoformat()
        now = self._now().isoformat()
        recovered: list[tuple[TaskRecord, str, str]] = []
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            rows = connection.execute(
                """
                SELECT t.*, e.error_code AS execution_error_code
                FROM tasks AS t
                JOIN worker_executions AS e ON e.task_id = t.task_id
                WHERE t.status = ? AND e.started_at < ?
                  AND (e.lease_expires_at IS NULL OR e.lease_expires_at <= ?)
                """,
                (TaskStatus.RUNNING.value, cutoff, now),
            ).fetchall()
            for row in rows:
                task = TaskRecord(
                    task_id=UUID(row["task_id"]),
                    task_type=row["task_type"],
                    status=TaskStatus.RUNNING,
                    risk_class=RiskClass(row["risk_class"]),
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                    description=row["description"],
                )
                workflow = connection.execute(
                    """
                    SELECT workflow_id, status FROM workflow_runs WHERE task_id = ?
                    """,
                    (str(task.task_id),),
                ).fetchone()
                if workflow is None:
                    recovered_status = TaskStatus.FAILED
                    audit_outcome = "failed"
                    reason_code = "worker_interrupted"
                    connection.execute(
                        """
                        UPDATE idempotency_records SET status = 'unknown_outcome'
                        WHERE task_id = ? AND status IN ('accepted', 'running')
                        """,
                        (str(task.task_id),),
                    )
                elif (
                    workflow["status"] == "running"
                    and row["execution_error_code"] == "cancellation_requested"
                ):
                    active_steps = connection.execute(
                        """
                        SELECT step_id, step_kind FROM workflow_steps
                        WHERE workflow_id = ? AND status = 'running'
                        """,
                        (workflow["workflow_id"],),
                    ).fetchall()
                    has_unknown_outcome = False
                    for step in active_steps:
                        safe_to_retry = step["step_kind"] in {
                            "provider_selection", "safe_tool"
                        }
                        attempt_status = "cancelled" if safe_to_retry else "unknown_outcome"
                        step_status = "cancelled" if safe_to_retry else "unknown_outcome"
                        if not safe_to_retry:
                            has_unknown_outcome = True
                        connection.execute(
                            """
                            UPDATE workflow_step_attempts
                            SET status = ?, error_code = 'cancelled_worker_interrupted',
                                finished_at = ?
                            WHERE step_id = ? AND status = 'running'
                            """,
                            (attempt_status, now, step["step_id"]),
                        )
                        connection.execute(
                            """
                            UPDATE workflow_steps
                            SET status = ?, error_code = 'cancelled_worker_interrupted',
                                finished_at = ?, updated_at = ?
                            WHERE step_id = ? AND status = 'running'
                            """,
                            (step_status, now, now, step["step_id"]),
                        )
                    if has_unknown_outcome:
                        workflow_status = "recovery_required"
                        recovered_status = TaskStatus.WAITING_APPROVAL
                        audit_outcome = "recovery_required"
                        reason_code = "cancelled_worker_interrupted_unknown_outcome"
                        connection.execute(
                            """
                            UPDATE idempotency_records SET status = 'unknown_outcome'
                            WHERE task_id = ? AND status IN ('accepted', 'running')
                            """,
                            (str(task.task_id),),
                        )
                    else:
                        workflow_status = "cancelled"
                        recovered_status = TaskStatus.CANCELLED
                        audit_outcome = "cancelled"
                        reason_code = "cancellation_completed_after_worker_interruption"
                        connection.execute(
                            "DELETE FROM workflow_payloads WHERE workflow_id = ?",
                            (workflow["workflow_id"],),
                        )
                        connection.execute(
                            """
                            UPDATE idempotency_records SET status = 'failed'
                            WHERE task_id = ? AND status IN ('accepted', 'running')
                            """,
                            (str(task.task_id),),
                        )
                    connection.execute(
                        """
                        UPDATE workflow_runs
                        SET status = ?, last_error_code = ?, updated_at = ?
                        WHERE workflow_id = ? AND status = 'running'
                        """,
                        (workflow_status, reason_code, now, workflow["workflow_id"]),
                    )
                elif workflow["status"] == "succeeded":
                    recovered_status = TaskStatus.SUCCEEDED
                    audit_outcome = "succeeded"
                    reason_code = "workflow_finished_before_job_commit"
                    connection.execute(
                        """
                        UPDATE idempotency_records SET status = 'completed'
                        WHERE task_id = ? AND status = 'running'
                        """,
                        (str(task.task_id),),
                    )
                elif workflow["status"] in {"failed", "cancelled"}:
                    recovered_status = (
                        TaskStatus.CANCELLED
                        if workflow["status"] == "cancelled"
                        else TaskStatus.FAILED
                    )
                    audit_outcome = workflow["status"]
                    reason_code = "workflow_terminal_before_job_commit"
                    connection.execute(
                        """
                        UPDATE idempotency_records SET status = 'failed'
                        WHERE task_id = ? AND status IN ('accepted', 'running')
                        """,
                        (str(task.task_id),),
                    )
                elif workflow["status"] in {"recovery_required", "waiting_approval"}:
                    recovered_status = TaskStatus.WAITING_APPROVAL
                    audit_outcome = "recovery_required"
                    reason_code = "workflow_recovery_already_required"
                else:
                    active_steps = connection.execute(
                        """
                        SELECT step_id, step_kind FROM workflow_steps
                        WHERE workflow_id = ? AND status = 'running'
                        """,
                        (workflow["workflow_id"],),
                    ).fetchall()
                    has_unknown_outcome = False
                    for step in active_steps:
                        safe_to_retry = step["step_kind"] in {
                            "provider_selection", "safe_tool"
                        }
                        attempt_status = "failed" if safe_to_retry else "unknown_outcome"
                        step_status = "retry_wait" if safe_to_retry else "unknown_outcome"
                        if not safe_to_retry:
                            has_unknown_outcome = True
                        connection.execute(
                            """
                            UPDATE workflow_step_attempts
                            SET status = ?, error_code = 'worker_interrupted', finished_at = ?
                            WHERE step_id = ? AND status = 'running'
                            """,
                            (attempt_status, now, step["step_id"]),
                        )
                        connection.execute(
                            """
                            UPDATE workflow_steps
                            SET status = ?, error_code = 'worker_interrupted',
                                finished_at = ?, updated_at = ?
                            WHERE step_id = ? AND status = 'running'
                            """,
                            (step_status, now, now, step["step_id"]),
                        )
                    workflow_status = (
                        "recovery_required" if has_unknown_outcome else "paused"
                    )
                    reason_code = (
                        "worker_interrupted"
                        if has_unknown_outcome
                        else "safe_step_interrupted"
                        if active_steps
                        else "worker_interrupted_before_step"
                    )
                    if has_unknown_outcome:
                        connection.execute(
                            """
                            UPDATE idempotency_records SET status = 'unknown_outcome'
                            WHERE task_id = ? AND status IN ('accepted', 'running')
                            """,
                            (str(task.task_id),),
                        )
                    connection.execute(
                        """
                        UPDATE workflow_runs
                        SET status = ?, last_error_code = ?, updated_at = ?
                        WHERE workflow_id = ? AND status IN ('queued', 'running', 'paused')
                        """,
                        (
                            workflow_status,
                            reason_code,
                            now,
                            workflow["workflow_id"],
                        ),
                    )
                    recovered_status = TaskStatus.WAITING_APPROVAL
                    audit_outcome = "recovery_required"

                cursor = connection.execute(
                    """
                    UPDATE tasks SET status = ?, updated_at = ?
                    WHERE task_id = ? AND status = ?
                    """,
                    (
                        recovered_status.value,
                        now,
                        str(task.task_id),
                        TaskStatus.RUNNING.value,
                    ),
                )
                if cursor.rowcount == 1:
                    connection.execute(
                        """
                        UPDATE worker_executions
                        SET error_code = ?, finished_at = ?, recovered_at = ?,
                            next_attempt_at = NULL
                        WHERE task_id = ?
                        """,
                        (reason_code, now, now, str(task.task_id)),
                    )
                    recovered.append((task, audit_outcome, reason_code))
        for task, outcome, reason_code in recovered:
            self._audit(task, outcome, reason_code)

    def _claim(self) -> TaskRecord | None:
        """Atomically claim one eligible queued task."""
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            now = self._now().isoformat()
            row = connection.execute(
                """
                SELECT t.* FROM tasks AS t
                LEFT JOIN worker_executions AS e ON e.task_id = t.task_id
                WHERE t.status = ?
                  AND (e.next_attempt_at IS NULL OR e.next_attempt_at <= ?)
                ORDER BY t.created_at LIMIT 1
                """,
                (TaskStatus.QUEUED.value, now),
            ).fetchone()
            if row is None:
                connection.commit()
                return None

            task = TaskRecord(
                task_id=UUID(row["task_id"]),
                task_type=row["task_type"],
                status=TaskStatus(row["status"]),
                risk_class=RiskClass(row["risk_class"]),
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                description=row["description"],
            )
            cursor = connection.execute(
                "UPDATE tasks SET status = ?, updated_at = ? WHERE task_id = ? AND status = ?",
                (
                    TaskStatus.RUNNING.value,
                    now,
                    str(task.task_id),
                    TaskStatus.QUEUED.value,
                ),
            )
            if cursor.rowcount != 1:
                connection.rollback()
                return None
            connection.execute(
                """
                INSERT INTO worker_executions (task_id, attempt_count, started_at)
                VALUES (?, 1, ?)
                ON CONFLICT(task_id) DO UPDATE SET
                    attempt_count = attempt_count + 1,
                    started_at = excluded.started_at,
                    error_code = NULL,
                    finished_at = NULL,
                    next_attempt_at = NULL
                """,
                (str(task.task_id), now),
            )
            connection.execute(
                """
                UPDATE idempotency_records SET status = 'running'
                WHERE task_id = ? AND status = 'accepted'
                """,
                (str(task.task_id),),
            )
            connection.commit()
            return task.model_copy(update={"status": TaskStatus.RUNNING, "updated_at": now})

    def run_once(self) -> TaskRecord | None:
        """Execute at most one eligible task; serialize calls through this worker instance."""
        with self._run_lock:
            return self._run_once()

    def _run_once(self) -> TaskRecord | None:
        self._recover_interrupted()
        task = self._claim()
        if task is None:
            return None

        lease = self._lease_manager.acquire(str(task.task_id), self._worker_id)
        if lease is None:
            # Another owner or inconsistent persisted state: never dispatch without ownership.
            return self.repository.get(task.task_id)

        stop_heartbeat = Event()
        lease_lost = Event()
        heartbeat = Thread(
            target=self._heartbeat_loop,
            args=(lease, stop_heartbeat, lease_lost),
            name=f"mrhub-lease-{task.task_id}",
            daemon=True,
        )
        heartbeat.start()
        try:
            if not self._lease_manager.is_current(lease):
                lease_lost.set()
                return self.repository.get(task.task_id)
            return self._execute_claimed(task, lease, lease_lost)
        finally:
            stop_heartbeat.set()
            heartbeat.join(timeout=max(1.0, self._lease_seconds))
            self._lease_manager.release(lease)

    def _heartbeat_loop(self, lease: WorkerLease, stop: Event, lease_lost: Event) -> None:
        interval = max(0.1, self._lease_seconds / 3)
        while not stop.wait(interval):
            if self._lease_manager.heartbeat(lease) is None:
                lease_lost.set()
                return

    def _execute_claimed(
        self, task: TaskRecord, lease: WorkerLease, lease_lost: Event
    ) -> TaskRecord | None:
        approval = self.repository.get_task_approval(task.task_id)
        if task.risk_class in {RiskClass.HIGH, RiskClass.PROHIBITED}:
            if task.risk_class is RiskClass.PROHIBITED:
                return self._finish_failure(task, "prohibited_task", lease=lease)
            if (
                approval is None
                or approval.get("decision") != "approved"
                or approval.get("action_fingerprint") != action_fingerprint(task)
            ):
                return self._finish_failure(task, "approval_missing_or_stale", lease=lease)

        current = self.repository.get(task.task_id)
        if current is None:
            raise WorkerError("Claimed task disappeared before dispatch")
        if current.status is TaskStatus.CANCELLED:
            self._mark_cancelled(task, lease=lease)
            return current

        if lease_lost.is_set():
            return self.repository.get(task.task_id)

        handler = self.handlers.get(task.task_type)
        if handler is None:
            return self._finish_failure(task, "handler_not_registered", lease=lease)

        try:
            if task.task_type == "agent.workflow":
                result = handler(task, lease, lease_lost)
            else:
                result = handler(task)
        except RetryableWorkerError:
            return self._schedule_retry_or_fail(task, lease=lease)
        except (ValueError, TypeError, KeyError):
            # Never persist exception text: it may contain private input or secrets.
            return self._finish_failure(task, "handler_failed", lease=lease)

        if lease_lost.is_set():
            return self.repository.get(task.task_id)

        # WorkflowRunner owns the workflow/job state transition. Persist its
        # sanitized result under the worker's lease even when the task is already
        # terminal, and do not overwrite paused/recovery-required states.
        after_handler = self.repository.get(task.task_id)
        if (
            task.task_type == "agent.workflow"
            and after_handler is not None
            and after_handler.status is not TaskStatus.RUNNING
        ):
            now = self._now().isoformat()
            if after_handler.status in {TaskStatus.SUCCEEDED, TaskStatus.CANCELLED}:
                # Persist the terminal outcome without changing the task state.
                # A cancellation must not leave worker_executions looking active,
                # nor may this post-handler path turn a cancelled task into success.
                terminal_success = after_handler.status is TaskStatus.SUCCEEDED
                with self._connection() as connection:
                    cursor = connection.execute(
                        """
                        UPDATE worker_executions
                        SET result_json = ?, error_code = ?, finished_at = ?,
                            next_attempt_at = NULL
                        WHERE task_id = ? AND lease_owner = ? AND execution_token = ?
                          AND lease_expires_at > ?
                        """,
                        (
                            json.dumps(result, ensure_ascii=False, sort_keys=True),
                            None if terminal_success else "cancelled_during_execution",
                            now,
                            str(task.task_id),
                            lease.owner,
                            lease.fencing_token,
                            now,
                        ),
                    )
                    if cursor.rowcount != 1:
                        raise WorkerError("Workflow result could not be persisted under its lease")
                    connection.execute(
                        """
                        UPDATE idempotency_records SET status = ?
                        WHERE task_id = ? AND status = 'running'
                        """,
                        ("completed" if terminal_success else "failed", str(task.task_id)),
                    )
                self._audit(
                    task,
                    "succeeded" if terminal_success else "cancelled",
                    "worker_completed" if terminal_success else "cancelled_during_execution",
                )
                return self.repository.get(task.task_id)
            return after_handler

        now = self._now().isoformat()
        with self._connection() as connection:
            cursor = connection.execute(
                """
                UPDATE tasks SET status = ?, updated_at = ?
                WHERE task_id = ? AND status = ?
                  AND EXISTS (
                    SELECT 1 FROM worker_executions AS e
                    WHERE e.task_id = tasks.task_id AND e.lease_owner = ?
                      AND e.execution_token = ? AND e.lease_expires_at > ?
                  )
                """,
                (TaskStatus.SUCCEEDED.value, now, str(task.task_id), TaskStatus.RUNNING.value,
                 lease.owner, lease.fencing_token, now),
            )
            if cursor.rowcount == 1:
                connection.execute(
                    """
                    UPDATE worker_executions
                    SET result_json = ?, error_code = NULL, finished_at = ?,
                        next_attempt_at = NULL
                    WHERE task_id = ?
                    """,
                    (
                        json.dumps(result, ensure_ascii=False, sort_keys=True),
                        now,
                        str(task.task_id),
                    ),
                )
                connection.execute(
                    """
                    UPDATE idempotency_records SET status = 'completed'
                    WHERE task_id = ? AND status = 'running'
                    """,
                    (str(task.task_id),),
                )
        saved = self.repository.get(task.task_id)
        if saved is None:
            raise WorkerError("Claimed task disappeared during execution")
        if saved.status is TaskStatus.SUCCEEDED:
            self._audit(task, "succeeded", "worker_completed")
        else:
            self._mark_cancelled(task, lease=lease)
        return saved

    def _schedule_retry_or_fail(
        self, task: TaskRecord, *, lease: WorkerLease
    ) -> TaskRecord:
        if task.task_type not in self.RETRY_SAFE_TASK_TYPES:
            return self._finish_failure(task, "retry_not_permitted", lease=lease)
        with self._connection() as connection:
            row = connection.execute(
                "SELECT attempt_count FROM worker_executions WHERE task_id = ?",
                (str(task.task_id),),
            ).fetchone()
        attempts = row["attempt_count"] if row else self.MAX_ATTEMPTS
        if attempts >= self.MAX_ATTEMPTS:
            return self._finish_failure(task, "retry_limit_exceeded", lease=lease)

        delay = min(
            self.RETRY_BASE_SECONDS * (2 ** max(attempts - 1, 0)),
            self.RETRY_MAX_SECONDS,
        )
        now = self._now()
        retry_at = (now + timedelta(seconds=delay)).isoformat()
        with self._connection() as connection:
            cursor = connection.execute(
                """
                UPDATE tasks SET status = ?, updated_at = ?
                WHERE task_id = ? AND status = ?
                  AND EXISTS (
                    SELECT 1 FROM worker_executions AS e
                    WHERE e.task_id = tasks.task_id AND e.lease_owner = ?
                      AND e.execution_token = ? AND e.lease_expires_at > ?
                  )
                """,
                (
                    TaskStatus.QUEUED.value,
                    now.isoformat(),
                    str(task.task_id),
                    TaskStatus.RUNNING.value,
                    lease.owner,
                    lease.fencing_token,
                    now.isoformat(),
                ),
            )
            if cursor.rowcount == 1:
                connection.execute(
                    """
                    UPDATE worker_executions
                    SET error_code = 'retry_scheduled', finished_at = NULL,
                        next_attempt_at = ?, result_json = NULL
                    WHERE task_id = ?
                    """,
                    (retry_at, str(task.task_id)),
                )
        saved = self.repository.get(task.task_id)
        if saved is None:
            raise WorkerError("Task disappeared while scheduling retry")
        if saved.status is TaskStatus.QUEUED:
            self._audit(task, "queued", "retry_scheduled")
        elif saved.status is TaskStatus.CANCELLED:
            self._mark_cancelled(task, lease=lease)
        return saved

    def _finish_failure(
        self, task: TaskRecord, error_code: str, *, lease: WorkerLease
    ) -> TaskRecord:
        now = self._now().isoformat()
        with self._connection() as connection:
            cursor = connection.execute(
                """
                UPDATE tasks SET status = ?, updated_at = ?
                WHERE task_id = ? AND status = ?
                  AND EXISTS (
                    SELECT 1 FROM worker_executions AS e
                    WHERE e.task_id = tasks.task_id AND e.lease_owner = ?
                      AND e.execution_token = ? AND e.lease_expires_at > ?
                  )
                """,
                (TaskStatus.FAILED.value, now, str(task.task_id), TaskStatus.RUNNING.value,
                 lease.owner, lease.fencing_token, now),
            )
            if cursor.rowcount == 1:
                connection.execute(
                    """
                    UPDATE worker_executions
                    SET error_code = ?, finished_at = ?, next_attempt_at = NULL
                    WHERE task_id = ?
                    """,
                    (error_code, now, str(task.task_id)),
                )
                idempotency_status = (
                    "unknown_outcome" if error_code == "handler_failed" else "failed"
                )
                connection.execute(
                    """
                    UPDATE idempotency_records SET status = ?
                    WHERE task_id = ? AND status IN ('accepted', 'running')
                    """,
                    (idempotency_status, str(task.task_id)),
                )
        saved = self.repository.get(task.task_id)
        if saved is None:
            raise WorkerError("Claimed task disappeared while recording failure")
        if saved.status is TaskStatus.FAILED:
            self._audit(task, "failed", error_code)
        elif saved.status is TaskStatus.CANCELLED:
            self._mark_cancelled(task, lease=lease)
        return saved

    def _mark_cancelled(self, task: TaskRecord, *, lease: WorkerLease) -> None:
        now = self._now().isoformat()
        with self._connection() as connection:
            connection.execute(
                """
                UPDATE worker_executions
                SET error_code = 'cancelled_during_execution', finished_at = ?,
                    next_attempt_at = NULL
                WHERE task_id = ? AND lease_owner = ? AND execution_token = ?
                  AND lease_expires_at > ?
                """,
                (now, str(task.task_id), lease.owner, lease.fencing_token, now),
            )
            connection.execute(
                """
                UPDATE idempotency_records SET status = 'failed'
                WHERE task_id = ? AND status IN ('accepted', 'running')
                """,
                (str(task.task_id),),
            )
        self._audit(task, "cancelled", "cancelled_during_execution")

    def _audit(self, task: TaskRecord, outcome: str, reason_code: str) -> None:
        new_status = {
            "succeeded": TaskStatus.SUCCEEDED.value,
            "cancelled": TaskStatus.CANCELLED.value,
            "failed": TaskStatus.FAILED.value,
            "queued": TaskStatus.QUEUED.value,
            "recovery_required": TaskStatus.WAITING_APPROVAL.value,
        }[outcome]
        AuditLogger(self.repository).record(
            event_type="task.worker_finished",
            outcome=outcome,
            subject_id=str(task.task_id),
            metadata={
                "task_type": task.task_type,
                "risk_class": task.risk_class.value,
                "reason_code": reason_code,
                "previous_status": TaskStatus.RUNNING.value,
                "new_status": new_status,
            },
        )

    def summary(self) -> dict[str, object]:
        """Return bounded queue metadata without exposing task descriptions or results."""
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT status, COUNT(*) AS total FROM tasks GROUP BY status"
            ).fetchall()
            retry_row = connection.execute(
                "SELECT COUNT(*) AS total FROM worker_executions "
                "WHERE next_attempt_at IS NOT NULL"
            ).fetchone()

        status_counts = {status.value: 0 for status in TaskStatus}
        for row in rows:
            status_counts[row["status"]] = row["total"]
        return {
            "total_tasks": sum(status_counts.values()),
            "status_counts": status_counts,
            "retry_scheduled": retry_row["total"] if retry_row else 0,
            "registered_handlers": sorted(self.handlers),
            "execution_mode": "pull_driven",
            "automatic_execution": False,
        }

    def get_result(self, task_id: UUID) -> dict[str, object] | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT result_json, error_code, attempt_count, started_at, finished_at, "
                "recovered_at, next_attempt_at FROM worker_executions WHERE task_id = ?",
                (str(task_id),),
            ).fetchone()
        if row is None:
            return None
        return {
            "result": json.loads(row["result_json"]) if row["result_json"] else None,
            "error_code": row["error_code"],
            "attempt_count": row["attempt_count"],
            "started_at": row["started_at"],
            "finished_at": row["finished_at"],
            "recovered_at": row["recovered_at"],
            "next_attempt_at": row["next_attempt_at"],
        }
