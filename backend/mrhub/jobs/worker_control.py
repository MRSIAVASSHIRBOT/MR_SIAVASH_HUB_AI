"""Durable global stop switch for worker dispatch."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class WorkerControlRepository:
    """Persist worker stop state in the same SQLite database as task claims."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    def get(self) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT stopped, reason, changed_by, changed_at FROM worker_control WHERE control_id = 1"
            ).fetchone()
        if row is None:
            raise RuntimeError("Worker control state is not initialized")
        return {
            "stopped": bool(row["stopped"]),
            "reason": row["reason"],
            "changed_by": row["changed_by"],
            "changed_at": row["changed_at"],
        }

    def set_stopped(
        self, stopped: bool, *, reason: str | None, changed_by: str
    ) -> dict[str, Any]:
        now = datetime.now(UTC).isoformat()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                """UPDATE worker_control
                   SET stopped = ?, reason = ?, changed_by = ?, changed_at = ?
                   WHERE control_id = 1""",
                (1 if stopped else 0, reason, changed_by, now),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("Worker control state is not initialized")
            connection.commit()
        return self.get()

    def is_stopped(self, connection: sqlite3.Connection | None = None) -> bool:
        if connection is not None:
            row = connection.execute(
                "SELECT stopped FROM worker_control WHERE control_id = 1"
            ).fetchone()
            if row is None:
                raise RuntimeError("Worker control state is not initialized")
            return bool(row["stopped"])
        return bool(self.get()["stopped"])
