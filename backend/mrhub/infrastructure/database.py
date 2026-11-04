"""SQLite persistence for the initial local-first runtime."""

import json
import sqlite3
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
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
        """Apply all pending, versioned schema migrations."""
        from mrhub.infrastructure.migrations import SchemaMigrator

        with self._connection() as connection:
            SchemaMigrator(connection).migrate()

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

    def update_status(
        self,
        task_id: UUID,
        expected: TaskStatus,
        updated: TaskRecord,
        *,
        lease_owner: str | None = None,
        fencing_token: int | None = None,
        lease_now: str | None = None,
    ) -> TaskRecord:
        """Compare-and-set status update, optionally fenced by durable worker ownership."""
        query = """
            UPDATE tasks
            SET status = ?, updated_at = ?
            WHERE task_id = ? AND status = ?
        """
        parameters: tuple[object, ...] = (
            updated.status.value,
            updated.updated_at.isoformat(),
            str(task_id),
            expected.value,
        )
        if lease_owner is not None or fencing_token is not None or lease_now is not None:
            if lease_owner is None or fencing_token is None or lease_now is None:
                raise ValueError("All lease fencing fields are required together")
            query += """
                AND EXISTS (
                    SELECT 1 FROM worker_executions AS e
                    WHERE e.task_id = tasks.task_id AND e.lease_owner = ?
                      AND e.execution_token = ? AND e.lease_expires_at > ?
                )
            """
            parameters += (lease_owner, fencing_token, lease_now)
        with self._connection() as connection:
            cursor = connection.execute(query, parameters)
            if cursor.rowcount != 1:
                raise RuntimeError(
                    "Task state or lease changed concurrently; reload before retrying"
                )
        return updated

    def record_audit(self, event: dict[str, object]) -> None:
        """Persist a sanitized audit event."""
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO audit_events (
                    event_id, event_type, outcome, subject_type,
                    subject_id, actor_type, actor_id, created_at, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event["event_id"],
                    event["event_type"],
                    event["outcome"],
                    event["subject_type"],
                    event["subject_id"],
                    event["actor_type"],
                    event.get("actor_id"),
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
                "actor_id": row["actor_id"],
                "created_at": row["created_at"],
                "metadata": json.loads(row["metadata_json"]),
            }
            for row in rows
        ]

    @staticmethod
    def _agent_model_run_record(row: sqlite3.Row) -> dict[str, object]:
        return {
            "run_id": row["subject_id"],
            "outcome": row["outcome"],
            "created_at": row["created_at"],
            "metadata": json.loads(row["metadata_json"]),
        }

    def list_agent_model_runs(self, owner_user_id: str, limit: int = 20) -> list[dict[str, object]]:
        """Return only model-run audit records belonging to the authenticated owner."""
        bounded_limit = max(1, min(limit, 100))
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT subject_id, outcome, created_at, metadata_json
                FROM audit_events
                WHERE event_type = 'agent.model_run'
                  AND subject_type = 'agent_run'
                  AND actor_type = 'user'
                  AND actor_id = ?
                ORDER BY created_at DESC, event_id DESC
                LIMIT ?
                """,
                (owner_user_id, bounded_limit),
            ).fetchall()
        return [self._agent_model_run_record(row) for row in rows]

    def get_agent_model_run(self, owner_user_id: str, run_id: str) -> dict[str, object] | None:
        """Return one model-run record only when it belongs to the authenticated owner."""
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT subject_id, outcome, created_at, metadata_json
                FROM audit_events
                WHERE event_type = 'agent.model_run'
                  AND subject_type = 'agent_run'
                  AND actor_type = 'user'
                  AND actor_id = ?
                  AND subject_id = ?
                ORDER BY created_at DESC, event_id DESC
                LIMIT 1
                """,
                (owner_user_id, run_id),
            ).fetchone()
        return self._agent_model_run_record(row) if row is not None else None

    def auth_user_exists(self) -> bool:
        with self._connection() as connection:
            return connection.execute("SELECT 1 FROM auth_users LIMIT 1").fetchone() is not None

    def create_auth_user(self, user_id: str, username: str, salt: str, password_hash: str) -> None:
        from datetime import UTC, datetime

        with self._connection() as connection:
            connection.execute(
                "INSERT INTO auth_users (user_id, username, salt, password_hash, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (user_id, username, salt, password_hash, datetime.now(UTC).isoformat()),
            )

    def get_auth_user(self, username: str) -> dict[str, str] | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT user_id, username, salt, password_hash FROM auth_users WHERE username = ?",
                (username,),
            ).fetchone()
        return dict(row) if row is not None else None

    def create_auth_session(
        self, session_id: str, user_id: str, token_hash: str, expires_at: str
    ) -> None:
        from datetime import UTC, datetime

        now = datetime.now(UTC).isoformat()
        with self._connection() as connection:
            # Expired bearer-token hashes are no longer useful; prune them on
            # session creation so abandoned sessions cannot accumulate forever.
            connection.execute(
                "DELETE FROM auth_sessions WHERE expires_at <= ?",
                (now,),
            )
            connection.execute(
                "INSERT INTO auth_sessions (session_id, user_id, token_hash, expires_at, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (session_id, user_id, token_hash, expires_at, now),
            )

    def get_auth_session(self, token_hash: str) -> dict[str, str] | None:
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT s.user_id, s.expires_at, u.username
                FROM auth_sessions AS s
                JOIN auth_users AS u ON u.user_id = s.user_id
                WHERE s.token_hash = ?
                """,
                (token_hash,),
            ).fetchone()
        return dict(row) if row is not None else None

    def delete_auth_session(self, token_hash: str) -> None:
        with self._connection() as connection:
            connection.execute("DELETE FROM auth_sessions WHERE token_hash = ?", (token_hash,))

    def record_task_approval(
        self,
        approval: dict[str, str],
        expected_status: TaskStatus,
        target_status: TaskStatus,
    ) -> None:
        """Persist one immutable, action-bound decision and transition atomically."""
        with self._connection() as connection:
            cursor = connection.execute(
                """
                UPDATE tasks SET status = ?, updated_at = ?
                WHERE task_id = ? AND status = ?
                """,
                (
                    target_status.value,
                    approval["created_at"],
                    approval["task_id"],
                    expected_status.value,
                ),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("Task is no longer awaiting this approval")
            connection.execute(
                """
                INSERT INTO task_approvals (
                    approval_id, task_id, decision, approver_id,
                    action_fingerprint, reason, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    approval["approval_id"],
                    approval["task_id"],
                    approval["decision"],
                    approval["approver_id"],
                    approval["action_fingerprint"],
                    approval["reason"],
                    approval["created_at"],
                ),
            )

    def get_task_approval(self, task_id: UUID) -> dict[str, str] | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM task_approvals WHERE task_id = ?",
                (str(task_id),),
            ).fetchone()
        return dict(row) if row is not None else None
