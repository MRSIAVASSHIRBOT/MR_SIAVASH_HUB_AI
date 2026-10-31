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
from threading import Lock
from uuid import UUID

from mrhub.domain.tasks import RiskClass, TaskRecord, TaskStatus
from mrhub.infrastructure.database import TaskRepository
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
    ) -> None:
        self.repository = repository
        self.database_path = repository.database_path
        self._run_lock = Lock()
        self._clock = clock or (lambda: datetime.now(UTC))
        self.handlers: dict[str, Callable[[TaskRecord], dict[str, str]]] = {
            "demo.echo": self._echo,
        }
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
        with self._connection() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS worker_executions (
                    task_id TEXT PRIMARY KEY REFERENCES tasks(task_id),
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    result_json TEXT,
                    error_code TEXT,
                    started_at TEXT,
                    finished_at TEXT
                )
                """
            )
            columns = {
                row["name"] for row in connection.execute(
                    "PRAGMA table_info(worker_executions)"
                )
            }
            if "recovered_at" not in columns:
                connection.execute(
                    "ALTER TABLE worker_executions ADD COLUMN recovered_at TEXT"
                )
            if "next_attempt_at" not in columns:
                connection.execute(
                    "ALTER TABLE worker_executions ADD COLUMN next_attempt_at TEXT"
                )

    @staticmethod
    def _echo(task: TaskRecord) -> dict[str, str]:
        return {"message": task.description, "task_type": task.task_type}

    def _recover_interrupted(self) -> None:
        """Fail stale running tasks rather than silently replaying possibly completed work."""
        cutoff = (self._now() - timedelta(seconds=self.STALE_AFTER_SECONDS)).isoformat()
        now = self._now().isoformat()
        recovered: list[TaskRecord] = []
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            rows = connection.execute(
                """
                SELECT t.* FROM tasks AS t
                JOIN worker_executions AS e ON e.task_id = t.task_id
                WHERE t.status = ? AND e.started_at < ?
                """,
                (TaskStatus.RUNNING.value, cutoff),
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
                cursor = connection.execute(
                    """
                    UPDATE tasks SET status = ?, updated_at = ?
                    WHERE task_id = ? AND status = ?
                    """,
                    (
                        TaskStatus.FAILED.value,
                        now,
                        str(task.task_id),
                        TaskStatus.RUNNING.value,
                    ),
                )
                if cursor.rowcount == 1:
                    connection.execute(
                        """
                        UPDATE worker_executions
                        SET error_code = 'worker_interrupted',
                            finished_at = ?, recovered_at = ?, next_attempt_at = NULL
                        WHERE task_id = ?
                        """,
                        (now, now, str(task.task_id)),
                    )
                    recovered.append(task)
        for task in recovered:
            self._audit(task, "failed", "worker_interrupted")

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

        approval = self.repository.get_task_approval(task.task_id)
        if task.risk_class in {RiskClass.HIGH, RiskClass.PROHIBITED}:
            if task.risk_class is RiskClass.PROHIBITED:
                return self._finish_failure(task, "prohibited_task")
            if (
                approval is None
                or approval.get("decision") != "approved"
                or approval.get("action_fingerprint") != action_fingerprint(task)
            ):
                return self._finish_failure(task, "approval_missing_or_stale")

        current = self.repository.get(task.task_id)
        if current is None:
            raise WorkerError("Claimed task disappeared before dispatch")
        if current.status is TaskStatus.CANCELLED:
            self._mark_cancelled(task)
            return current

        handler = self.handlers.get(task.task_type)
        if handler is None:
            return self._finish_failure(task, "handler_not_registered")

        try:
            result = handler(task)
        except RetryableWorkerError:
            return self._schedule_retry_or_fail(task)
        except Exception:
            # Never persist exception text: it may contain private input or secrets.
            return self._finish_failure(task, "handler_failed")

        now = self._now().isoformat()
        with self._connection() as connection:
            cursor = connection.execute(
                """
                UPDATE tasks SET status = ?, updated_at = ?
                WHERE task_id = ? AND status = ?
                """,
                (TaskStatus.SUCCEEDED.value, now, str(task.task_id), TaskStatus.RUNNING.value),
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
        saved = self.repository.get(task.task_id)
        if saved is None:
            raise WorkerError("Claimed task disappeared during execution")
        if saved.status is TaskStatus.SUCCEEDED:
            self._audit(task, "succeeded", "worker_completed")
        else:
            self._mark_cancelled(task)
        return saved

    def _schedule_retry_or_fail(self, task: TaskRecord) -> TaskRecord:
        if task.task_type not in self.RETRY_SAFE_TASK_TYPES:
            return self._finish_failure(task, "retry_not_permitted")
        with self._connection() as connection:
            row = connection.execute(
                "SELECT attempt_count FROM worker_executions WHERE task_id = ?",
                (str(task.task_id),),
            ).fetchone()
        attempts = row["attempt_count"] if row else self.MAX_ATTEMPTS
        if attempts >= self.MAX_ATTEMPTS:
            return self._finish_failure(task, "retry_limit_exceeded")

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
                """,
                (
                    TaskStatus.QUEUED.value,
                    now.isoformat(),
                    str(task.task_id),
                    TaskStatus.RUNNING.value,
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
            self._mark_cancelled(task)
        return saved

    def _finish_failure(self, task: TaskRecord, error_code: str) -> TaskRecord:
        now = self._now().isoformat()
        with self._connection() as connection:
            cursor = connection.execute(
                """
                UPDATE tasks SET status = ?, updated_at = ?
                WHERE task_id = ? AND status = ?
                """,
                (TaskStatus.FAILED.value, now, str(task.task_id), TaskStatus.RUNNING.value),
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
        saved = self.repository.get(task.task_id)
        if saved is None:
            raise WorkerError("Claimed task disappeared while recording failure")
        if saved.status is TaskStatus.FAILED:
            self._audit(task, "failed", error_code)
        elif saved.status is TaskStatus.CANCELLED:
            self._mark_cancelled(task)
        return saved

    def _mark_cancelled(self, task: TaskRecord) -> None:
        now = self._now().isoformat()
        with self._connection() as connection:
            connection.execute(
                """
                UPDATE worker_executions
                SET error_code = 'cancelled_during_execution', finished_at = ?,
                    next_attempt_at = NULL
                WHERE task_id = ?
                """,
                (now, str(task.task_id)),
            )
        self._audit(task, "cancelled", "cancelled_during_execution")

    def _audit(self, task: TaskRecord, outcome: str, reason_code: str) -> None:
        new_status = {
            "succeeded": TaskStatus.SUCCEEDED.value,
            "cancelled": TaskStatus.CANCELLED.value,
            "failed": TaskStatus.FAILED.value,
            "queued": TaskStatus.QUEUED.value,
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
