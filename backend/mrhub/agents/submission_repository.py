"""Atomic, owner-scoped idempotency reservations for workflow submissions.

Only identifiers and a request digest are persisted here; request bodies and tool
arguments must never be stored by this repository.
"""
from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class IdempotencyConflict(ValueError):
    """Raised when an idempotency key is reused for a different request."""


class SubmissionStateError(RuntimeError):
    """Raised when a reservation cannot make the requested state transition."""


class WorkflowSubmissionRepository:
    """Persist workflow submission keys with SQLite transaction-level serialization."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = Path(database_path)

    def _connect(self) -> sqlite3.Connection:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.database_path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 5000")
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def initialize(self) -> None:
        """Apply the canonical versioned schema; do not create tables ad hoc."""
        from mrhub.infrastructure.database import TaskRepository

        TaskRepository(self.database_path).initialize()

    def reserve(
        self,
        owner_user_id: str,
        endpoint: str,
        idempotency_key: str,
        request_digest: str,
    ) -> dict[str, Any]:
        """Atomically reserve a key or return its existing state.

        The caller must treat 'reserved' as in-progress and must not execute the
        workflow again. A digest mismatch fails closed instead of reusing a key.
        """
        self._validate(owner_user_id, "owner_user_id")
        self._validate(endpoint, "endpoint")
        self._validate(idempotency_key, "idempotency_key")
        self._validate(request_digest, "request_digest")
        now = datetime.now(UTC).isoformat()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """SELECT request_digest, state, workflow_id, task_id, created_at, updated_at
                   FROM workflow_submission_keys
                   WHERE owner_user_id = ? AND endpoint = ? AND idempotency_key = ?""",
                (owner_user_id, endpoint, idempotency_key),
            ).fetchone()
            if row is not None:
                if row["request_digest"] != request_digest:
                    raise IdempotencyConflict(
                        "Idempotency key was already used with a different request"
                    )
                return self._as_dict(row, created=False)

            connection.execute(
                """INSERT INTO workflow_submission_keys
                   (owner_user_id, endpoint, idempotency_key, request_digest, state,
                    workflow_id, task_id, created_at, updated_at)
                   VALUES (?, ?, ?, ?, 'reserved', NULL, NULL, ?, ?)""",
                (owner_user_id, endpoint, idempotency_key, request_digest, now, now),
            )
            return {
                "state": "reserved",
                "workflow_id": None,
                "task_id": None,
                "created_at": now,
                "updated_at": now,
                "created": True,
            }

    def bind(
        self,
        owner_user_id: str,
        endpoint: str,
        idempotency_key: str,
        request_digest: str,
        workflow_id: str,
        task_id: str,
    ) -> dict[str, Any]:
        """Bind a reservation to the created workflow and task exactly once."""
        for value, name in (
            (owner_user_id, "owner_user_id"),
            (endpoint, "endpoint"),
            (idempotency_key, "idempotency_key"),
            (request_digest, "request_digest"),
            (workflow_id, "workflow_id"),
            (task_id, "task_id"),
        ):
            self._validate(value, name)
        now = datetime.now(UTC).isoformat()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """SELECT request_digest, state, workflow_id, task_id, created_at, updated_at
                   FROM workflow_submission_keys
                   WHERE owner_user_id = ? AND endpoint = ? AND idempotency_key = ?""",
                (owner_user_id, endpoint, idempotency_key),
            ).fetchone()
            if row is None:
                raise SubmissionStateError("Workflow submission reservation does not exist")
            if row["request_digest"] != request_digest:
                raise IdempotencyConflict(
                    "Idempotency key was already used with a different request"
                )
            if row["state"] == "bound":
                if row["workflow_id"] != workflow_id or row["task_id"] != task_id:
                    raise SubmissionStateError("Reservation is already bound to another execution")
                return self._as_dict(row, created=False)
            if row["state"] != "reserved":
                raise SubmissionStateError("Only a reserved submission can be bound")
            connection.execute(
                """UPDATE workflow_submission_keys
                   SET state = 'bound', workflow_id = ?, task_id = ?, updated_at = ?
                   WHERE owner_user_id = ? AND endpoint = ? AND idempotency_key = ?
                     AND state = 'reserved'""",
                (workflow_id, task_id, now, owner_user_id, endpoint, idempotency_key),
            )
            return {
                "state": "bound",
                "workflow_id": workflow_id,
                "task_id": task_id,
                "created_at": row["created_at"],
                "updated_at": now,
                "created": False,
            }

    def mark_failed(
        self,
        owner_user_id: str,
        endpoint: str,
        idempotency_key: str,
        request_digest: str,
    ) -> None:
        """Mark an unbound reservation failed; never rewrite a bound execution."""
        now = datetime.now(UTC).isoformat()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                """UPDATE workflow_submission_keys SET state = 'failed', updated_at = ?
                   WHERE owner_user_id = ? AND endpoint = ? AND idempotency_key = ?
                     AND request_digest = ? AND state = 'reserved'""",
                (now, owner_user_id, endpoint, idempotency_key, request_digest),
            )
            if cursor.rowcount != 1:
                row = connection.execute(
                    """SELECT request_digest, state FROM workflow_submission_keys
                       WHERE owner_user_id = ? AND endpoint = ? AND idempotency_key = ?""",
                    (owner_user_id, endpoint, idempotency_key),
                ).fetchone()
                if row is None:
                    raise SubmissionStateError("Workflow submission reservation does not exist")
                if row["request_digest"] != request_digest:
                    raise IdempotencyConflict(
                        "Idempotency key was already used with a different request"
                    )
                raise SubmissionStateError("Only a reserved submission can be marked failed")

    @staticmethod
    def _validate(value: str, name: str) -> None:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} must be a non-empty string")

    @staticmethod
    def _as_dict(row: sqlite3.Row, *, created: bool) -> dict[str, Any]:
        return {
            "state": row["state"],
            "workflow_id": row["workflow_id"],
            "task_id": row["task_id"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "created": created,
        }
