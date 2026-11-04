"""Durable idempotency reservations for jobs and workflow submissions."""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import ClassVar

from mrhub.domain.tasks import TaskRecord


class IdempotencyError(ValueError):
    """Raised when an idempotency operation violates its contract."""


class IdempotencyConflict(IdempotencyError):
    """Raised when a key is reused for a different request or resource."""


@dataclass(frozen=True)
class IdempotencyRecord:
    scope: str
    key: str
    request_digest: str
    task_id: str | None
    workflow_id: str | None
    status: str
    created_at: str
    expires_at: str | None


@dataclass(frozen=True)
class IdempotencyReservation:
    record: IdempotencyRecord
    created: bool


class IdempotencyRepository:
    """Reserve request keys atomically without persisting request payloads."""

    _ALLOWED_TRANSITIONS: ClassVar[dict[str, set[str]]] = {
        "accepted": {"running", "failed"},
        "running": {"completed", "failed", "unknown_outcome"},
        "completed": set(),
        "failed": set(),
        "unknown_outcome": set(),
    }
    _DIGEST_PATTERN = re.compile(r"^[0-9a-f]{64}$")

    def __init__(
        self,
        database_path: Path,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.database_path = database_path
        self._clock = clock or (lambda: datetime.now(UTC))

    def _now(self) -> str:
        value = self._clock()
        if value.tzinfo is None:
            raise IdempotencyError("Idempotency clock must return a timezone-aware datetime")
        return value.astimezone(UTC).isoformat()

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

    @classmethod
    def _validate(cls, scope: str, key: str, request_digest: str) -> None:
        if not scope.strip() or len(scope) > 120:
            raise IdempotencyError("Scope must contain 1 to 120 nonblank characters")
        if not key.strip() or len(key) > 255:
            raise IdempotencyError("Idempotency key must contain 1 to 255 nonblank characters")
        if not cls._DIGEST_PATTERN.fullmatch(request_digest):
            raise IdempotencyError("Request digest must be a lowercase SHA-256 hex digest")

    @staticmethod
    def _record(row: sqlite3.Row) -> IdempotencyRecord:
        return IdempotencyRecord(
            scope=row["scope"],
            key=row["idempotency_key"],
            request_digest=row["request_digest"],
            task_id=row["task_id"],
            workflow_id=row["workflow_id"],
            status=row["status"],
            created_at=row["created_at"],
            expires_at=row["expires_at"],
        )

    def reserve(
        self,
        scope: str,
        key: str,
        request_digest: str,
        *,
        task_id: str | None = None,
        workflow_id: str | None = None,
    ) -> IdempotencyReservation:
        """Create one reservation or return the matching existing reservation."""
        self._validate(scope, key, request_digest)
        if task_id is not None and not task_id.strip():
            raise IdempotencyError("Task id cannot be blank")
        if workflow_id is not None and not workflow_id.strip():
            raise IdempotencyError("Workflow id cannot be blank")

        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT * FROM idempotency_records
                WHERE scope = ? AND idempotency_key = ?
                """,
                (scope, key),
            ).fetchone()
            if row is not None:
                existing = self._record(row)
                if existing.request_digest != request_digest:
                    raise IdempotencyConflict(
                        "Idempotency key was already used for a different request"
                    )
                if existing.task_id not in {None, task_id} and task_id is not None:
                    raise IdempotencyConflict("Idempotency key is already bound to another task")
                if existing.workflow_id not in {None, workflow_id} and workflow_id is not None:
                    raise IdempotencyConflict(
                        "Idempotency key is already bound to another workflow"
                    )
                if (task_id is not None and existing.task_id is None) or (
                    workflow_id is not None and existing.workflow_id is None
                ):
                    connection.execute(
                        """
                        UPDATE idempotency_records
                        SET task_id = COALESCE(task_id, ?),
                            workflow_id = COALESCE(workflow_id, ?)
                        WHERE scope = ? AND idempotency_key = ?
                        """,
                        (task_id, workflow_id, scope, key),
                    )
                    row = connection.execute(
                        """
                        SELECT * FROM idempotency_records
                        WHERE scope = ? AND idempotency_key = ?
                        """,
                        (scope, key),
                    ).fetchone()
                    existing = self._record(row)
                return IdempotencyReservation(existing, created=False)

            created_at = self._now()
            connection.execute(
                """
                INSERT INTO idempotency_records (
                    scope, idempotency_key, request_digest, task_id,
                    workflow_id, status, created_at, expires_at
                ) VALUES (?, ?, ?, ?, ?, 'accepted', ?, NULL)
                """,
                (scope, key, request_digest, task_id, workflow_id, created_at),
            )
            row = connection.execute(
                """
                SELECT * FROM idempotency_records
                WHERE scope = ? AND idempotency_key = ?
                """,
                (scope, key),
            ).fetchone()
            return IdempotencyReservation(self._record(row), created=True)

    def reserve_task(
        self,
        scope: str,
        key: str,
        request_digest: str,
        task: TaskRecord,
    ) -> IdempotencyReservation:
        """Atomically create a task and bind it to a new idempotency reservation."""
        self._validate(scope, key, request_digest)
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT * FROM idempotency_records
                WHERE scope = ? AND idempotency_key = ?
                """,
                (scope, key),
            ).fetchone()
            if row is not None:
                existing = self._record(row)
                if existing.request_digest != request_digest:
                    raise IdempotencyConflict(
                        "Idempotency key was already used for a different request"
                    )
                if existing.workflow_id is not None:
                    raise IdempotencyConflict("Idempotency key is already bound to a workflow")
                if existing.task_id is not None:
                    return IdempotencyReservation(existing, created=False)

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
            if row is None:
                connection.execute(
                    """
                    INSERT INTO idempotency_records (
                        scope, idempotency_key, request_digest, task_id,
                        workflow_id, status, created_at, expires_at
                    ) VALUES (?, ?, ?, ?, NULL, 'accepted', ?, NULL)
                    """,
                    (scope, key, request_digest, str(task.task_id), self._now()),
                )
            else:
                connection.execute(
                    """
                    UPDATE idempotency_records SET task_id = ?
                    WHERE scope = ? AND idempotency_key = ? AND task_id IS NULL
                    """,
                    (str(task.task_id), scope, key),
                )
            saved = connection.execute(
                """
                SELECT * FROM idempotency_records
                WHERE scope = ? AND idempotency_key = ?
                """,
                (scope, key),
            ).fetchone()
            return IdempotencyReservation(self._record(saved), created=True)

    def get(self, scope: str, key: str) -> IdempotencyRecord | None:
        if not scope or not key:
            raise IdempotencyError("Scope and key are required")
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT * FROM idempotency_records
                WHERE scope = ? AND idempotency_key = ?
                """,
                (scope, key),
            ).fetchone()
        return self._record(row) if row is not None else None

    def bind(
        self,
        scope: str,
        key: str,
        *,
        task_id: str | None = None,
        workflow_id: str | None = None,
    ) -> IdempotencyRecord:
        """Attach resource identifiers once; never silently replace an existing link."""
        if task_id is None and workflow_id is None:
            raise IdempotencyError("At least one resource identifier is required")
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT * FROM idempotency_records
                WHERE scope = ? AND idempotency_key = ?
                """,
                (scope, key),
            ).fetchone()
            if row is None:
                raise LookupError("Idempotency reservation not found")
            current = self._record(row)
            if current.task_id not in {None, task_id} and task_id is not None:
                raise IdempotencyConflict("Reservation is already bound to another task")
            if current.workflow_id not in {None, workflow_id} and workflow_id is not None:
                raise IdempotencyConflict("Reservation is already bound to another workflow")
            connection.execute(
                """
                UPDATE idempotency_records
                SET task_id = COALESCE(task_id, ?),
                    workflow_id = COALESCE(workflow_id, ?)
                WHERE scope = ? AND idempotency_key = ?
                """,
                (task_id, workflow_id, scope, key),
            )
            updated = connection.execute(
                """
                SELECT * FROM idempotency_records
                WHERE scope = ? AND idempotency_key = ?
                """,
                (scope, key),
            ).fetchone()
            return self._record(updated)

    def transition(self, scope: str, key: str, expected: str, target: str) -> IdempotencyRecord:
        """Apply a compare-and-set state transition; unknown outcomes are never retried."""
        if target not in self._ALLOWED_TRANSITIONS.get(expected, set()):
            raise IdempotencyError(f"Invalid idempotency transition: {expected} -> {target}")
        with self._connection() as connection:
            cursor = connection.execute(
                """
                UPDATE idempotency_records SET status = ?
                WHERE scope = ? AND idempotency_key = ? AND status = ?
                """,
                (target, scope, key, expected),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("Idempotency state changed; reload before retrying")
            row = connection.execute(
                """
                SELECT * FROM idempotency_records
                WHERE scope = ? AND idempotency_key = ?
                """,
                (scope, key),
            ).fetchone()
            return self._record(row)

    def resolve_unknown(self, scope: str, key: str, outcome: str) -> IdempotencyRecord:
        """Record a reconciled outcome; this does not execute or replay the request."""
        if outcome not in {"completed", "failed"}:
            raise IdempotencyError("Unknown outcomes can only be reconciled to completed or failed")
        with self._connection() as connection:
            cursor = connection.execute(
                """
                UPDATE idempotency_records SET status = ?
                WHERE scope = ? AND idempotency_key = ? AND status = 'unknown_outcome'
                """,
                (outcome, scope, key),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("Unknown outcome changed; reconcile the current record")
            row = connection.execute(
                """
                SELECT * FROM idempotency_records
                WHERE scope = ? AND idempotency_key = ?
                """,
                (scope, key),
            ).fetchone()
            return self._record(row)
