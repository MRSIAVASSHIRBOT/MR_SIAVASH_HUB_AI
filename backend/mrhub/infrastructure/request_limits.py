"""Durable per-owner request throttling backed by SQLite transactions."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from math import ceil
from pathlib import Path

from mrhub.infrastructure.database import TaskRepository


class KimiRequestRateLimitRepository:
    """Atomically reserve per-owner Kimi requests across shared-DB API processes."""

    def __init__(
        self,
        database_path: Path,
        *,
        max_requests: int = 10,
        window_seconds: int = 60,
    ) -> None:
        if any(
            isinstance(value, bool) or not isinstance(value, int) or value < 1
            for value in (max_requests, window_seconds)
        ):
            raise ValueError("Rate limiter bounds must be positive integers")
        self.database_path = Path(database_path)
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        # Ensure the versioned migration is applied before querying the table.
        TaskRepository(self.database_path).initialize()

    def consume(self, owner_id: str) -> int | None:
        """Reserve one request or return a Retry-After value without sleeping."""
        if not isinstance(owner_id, str) or not owner_id or len(owner_id) > 200:
            raise ValueError("Rate limiter owner identifier is invalid")

        now = datetime.now(UTC)
        cutoff_text = (now - timedelta(seconds=self.window_seconds)).isoformat()
        now_text = now.isoformat()
        connection = sqlite3.connect(self.database_path, timeout=5.0)
        try:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA busy_timeout = 5000")
            # BEGIN IMMEDIATE serializes competing reservations across threads
            # and distinct API processes sharing this SQLite database file.
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "DELETE FROM kimi_request_events WHERE requested_at <= ?",
                (cutoff_text,),
            )
            row = connection.execute(
                """SELECT COUNT(*) AS request_count, MIN(requested_at) AS oldest
                   FROM kimi_request_events
                   WHERE owner_user_id = ? AND requested_at > ?""",
                (owner_id, cutoff_text),
            ).fetchone()
            if int(row["request_count"]) >= self.max_requests:
                oldest = datetime.fromisoformat(str(row["oldest"]))
                retry_after = self.window_seconds - (now - oldest).total_seconds()
                connection.commit()
                return max(1, ceil(retry_after))

            connection.execute(
                """INSERT INTO kimi_request_events(owner_user_id, requested_at)
                   VALUES (?, ?)""",
                (owner_id, now_text),
            )
            connection.commit()
            return None
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
