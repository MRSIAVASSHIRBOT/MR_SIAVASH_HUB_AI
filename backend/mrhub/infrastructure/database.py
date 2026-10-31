"""SQLite persistence for the initial local-first runtime."""

import json
import sqlite3
from contextlib import contextmanager
from collections.abc import Iterable, Iterator
from pathlib import Path
from uuid import UUID

from mrhub.domain.tasks import RiskClass, TaskRecord, TaskStatus


class TaskRepository:
    """Small repository abstraction; each operation owns its connection."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    def _connect(self) -> sqlite3.Connection:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
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

    def initialize(self) -> None:
        with self._connection() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    task_id TEXT PRIMARY KEY,
                    task_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    risk_class TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    description TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_tasks_created_at ON tasks(created_at)"
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS audit_events (
                    event_id TEXT PRIMARY KEY,
                    event_type TEXT NOT NULL,
                    outcome TEXT NOT NULL,
                    subject_type TEXT NOT NULL,
                    subject_id TEXT,
                    actor_type TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    metadata_json TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_audit_created_at ON audit_events(created_at)"
            )

    def create(self, task: TaskRecord) -> TaskRecord:
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO tasks (
                    task_id, task_type, status, risk_class,
                    created_at, updated_at, description
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(task.task_id),
                    task.task_type,
                    task.status.value,
                    task.risk_class.value,
                    task.created_at.isoformat(),
                    task.updated_at.isoformat(),
                    task.description,
                ),
            )
        return task

    def get(self, task_id: UUID) -> TaskRecord | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM tasks WHERE task_id = ?", (str(task_id),)
            ).fetchone()
        if row is None:
            return None
        return TaskRecord(
            task_id=UUID(row["task_id"]),
            task_type=row["task_type"],
            status=TaskStatus(row["status"]),
            risk_class=RiskClass(row["risk_class"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            description=row["description"],
        )

    def list_recent(self, limit: int = 50) -> Iterable[TaskRecord]:
        bounded_limit = max(1, min(limit, 100))
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM tasks ORDER BY created_at DESC LIMIT ?",
                (bounded_limit,),
            ).fetchall()
        return [
            TaskRecord(
                task_id=UUID(row["task_id"]),
                task_type=row["task_type"],
                status=TaskStatus(row["status"]),
                risk_class=RiskClass(row["risk_class"]),
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                description=row["description"],
            )
            for row in rows
        ]

    def update_status(self, task_id: UUID, expected: TaskStatus, updated: TaskRecord) -> TaskRecord:
        """Compare-and-set status update prevents concurrent invalid transitions."""
        with self._connection() as connection:
            cursor = connection.execute(
                """
                UPDATE tasks
                SET status = ?, updated_at = ?
                WHERE task_id = ? AND status = ?
                """,
                (
                    updated.status.value,
                    updated.updated_at.isoformat(),
                    str(task_id),
                    expected.value,
                ),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("Task state changed concurrently; reload before retrying")
        return updated

    def record_audit(self, event: dict[str, object]) -> None:
        """Persist a sanitized audit event."""
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO audit_events (
                    event_id, event_type, outcome, subject_type,
                    subject_id, actor_type, created_at, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event["event_id"],
                    event["event_type"],
                    event["outcome"],
                    event["subject_type"],
                    event["subject_id"],
                    event["actor_type"],
                    event["created_at"],
                    json.dumps(event["metadata"], ensure_ascii=False, sort_keys=True),
                ),
            )

    def list_audit(self, limit: int = 100) -> list[dict[str, object]]:
        """Return recent audit events for internal diagnostics."""
        bounded_limit = max(1, min(limit, 500))
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM audit_events ORDER BY created_at DESC LIMIT ?",
                (bounded_limit,),
            ).fetchall()
        return [
            {
                "event_id": row["event_id"],
                "event_type": row["event_type"],
                "outcome": row["outcome"],
                "subject_type": row["subject_type"],
                "subject_id": row["subject_id"],
                "actor_type": row["actor_type"],
                "created_at": row["created_at"],
                "metadata": json.loads(row["metadata_json"]),
            }
            for row in rows
        ]
