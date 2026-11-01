"""Durable SQLite worker leases with monotonically increasing fencing tokens."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path


class LeaseError(RuntimeError):
    """Raised when lease parameters or database state are invalid."""


@dataclass(frozen=True)
class WorkerLease:
    task_id: str
    owner: str
    fencing_token: int
    expires_at: str


class LeaseManager:
    """Coordinates worker ownership across processes using SQLite compare-and-set."""

    def __init__(
        self,
        database_path: Path,
        *,
        lease_seconds: int = 60,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if lease_seconds < 1:
            raise LeaseError("Lease duration must be positive")
        self.database_path = database_path
        self.lease_seconds = lease_seconds
        self._clock = clock or (lambda: datetime.now(UTC))

    def _now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None:
            raise LeaseError("Lease clock must return a timezone-aware datetime")
        return value.astimezone(UTC)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    def acquire(self, task_id: str, owner: str) -> WorkerLease | None:
        """Acquire an unowned/expired lease for a task already claimed as running."""
        if not task_id.strip() or not owner.strip():
            raise LeaseError("Task id and worker owner are required")

        now = self._now()
        now_text = now.isoformat()
        expires_text = (now + timedelta(seconds=self.lease_seconds)).isoformat()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT t.status, e.lease_owner, e.lease_expires_at,
                       COALESCE(e.execution_token, 0) AS fencing_token
                FROM tasks AS t
                JOIN worker_executions AS e ON e.task_id = t.task_id
                WHERE t.task_id = ?
                """,
                (task_id,),
            ).fetchone()
            if row is None or row["status"] != "running":
                return None
            if (
                row["lease_owner"] is not None
                and row["lease_expires_at"] is not None
                and row["lease_expires_at"] > now_text
            ):
                return None

            next_token = int(row["fencing_token"]) + 1
            cursor = connection.execute(
                """
                UPDATE worker_executions
                SET lease_owner = ?, lease_expires_at = ?, heartbeat_at = ?,
                    execution_token = ?
                WHERE task_id = ?
                  AND COALESCE(execution_token, 0) = ?
                  AND (
                    lease_owner IS NULL OR lease_expires_at IS NULL
                    OR lease_expires_at <= ?
                  )
                """,
                (
                    owner,
                    expires_text,
                    now_text,
                    next_token,
                    task_id,
                    row["fencing_token"],
                    now_text,
                ),
            )
            if cursor.rowcount != 1:
                return None
            return WorkerLease(task_id, owner, next_token, expires_text)

    def heartbeat(self, lease: WorkerLease) -> WorkerLease | None:
        """Renew only the current, unexpired owner/token pair."""
        now = self._now()
        now_text = now.isoformat()
        expires_text = (now + timedelta(seconds=self.lease_seconds)).isoformat()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                """
                UPDATE worker_executions
                SET heartbeat_at = ?, lease_expires_at = ?
                WHERE task_id = ? AND lease_owner = ? AND execution_token = ?
                  AND lease_expires_at > ?
                """,
                (
                    now_text,
                    expires_text,
                    lease.task_id,
                    lease.owner,
                    lease.fencing_token,
                    now_text,
                ),
            )
            if cursor.rowcount != 1:
                return None
        return WorkerLease(lease.task_id, lease.owner, lease.fencing_token, expires_text)

    def release(self, lease: WorkerLease) -> bool:
        """Release only the lease still owned by this exact fencing token."""
        now_text = self._now().isoformat()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                """
                UPDATE worker_executions
                SET lease_owner = NULL, lease_expires_at = NULL, heartbeat_at = ?
                WHERE task_id = ? AND lease_owner = ? AND execution_token = ?
                """,
                (now_text, lease.task_id, lease.owner, lease.fencing_token),
            )
            return cursor.rowcount == 1

    def is_current(self, lease: WorkerLease) -> bool:
        """Check whether the exact owner/token still holds an unexpired lease."""
        now_text = self._now().isoformat()
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT 1 FROM worker_executions
                WHERE task_id = ? AND lease_owner = ? AND execution_token = ?
                  AND lease_expires_at > ?
                """,
                (lease.task_id, lease.owner, lease.fencing_token, now_text),
            ).fetchone()
        return row is not None
