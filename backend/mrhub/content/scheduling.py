"""Durable owner-scoped schedule records for approved content drafts."""

from __future__ import annotations

import hashlib
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from mrhub.content.repository import ContentDraftRepository


class ScheduleConflict(ValueError):
    """Raised when a draft cannot be scheduled in its current state."""


class ContentScheduleRepository:
    """Persist schedules only; delivery is performed by a separately registered worker."""

    def __init__(self, database_path: Path) -> None:
        self.drafts = ContentDraftRepository(database_path)
        self.tasks = self.drafts.tasks

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()

    @staticmethod
    def _record(row) -> dict[str, object]:
        return {
            "schedule_id": row["schedule_id"],
            "draft_id": row["draft_id"],
            "platform": row["platform"],
            "scheduled_at": row["scheduled_at"],
            "status": row["status"],
            "draft_version": row["draft_version"],
            "content_hash": row["content_hash"],
            "attempt_count": row["attempt_count"],
            "last_error_code": row["last_error_code"],
            "provider_post_id": row["provider_post_id"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "published_at": row["published_at"],
        }

    def schedule(
        self, owner_user_id: str, draft_id: UUID, scheduled_at: datetime
    ) -> dict[str, object]:
        if scheduled_at.tzinfo is None or scheduled_at.utcoffset() is None:
            raise ScheduleConflict("scheduled_at must include a timezone")
        scheduled_utc = scheduled_at.astimezone(UTC)
        now = datetime.now(UTC)
        if scheduled_utc <= now:
            raise ScheduleConflict("scheduled_at must be in the future")

        draft = self.drafts.get(owner_user_id, draft_id)
        if draft is None:
            raise KeyError("Content draft not found")
        if draft["status"] != "approved":
            raise ScheduleConflict("Only approved drafts can be scheduled")
        if draft["platform"] == "generic":
            raise ScheduleConflict("Generic drafts cannot be scheduled for external publishing")

        schedule_id = str(uuid4())
        created_at = self._now()
        idempotency_key = hashlib.sha256(
            f"{owner_user_id}:{draft_id}:{draft['version']}:{scheduled_utc.isoformat()}".encode()
        ).hexdigest()
        try:
            with self.tasks._connection() as connection:
                connection.execute(
                    """
                    INSERT INTO content_publish_schedules (
                        schedule_id, owner_user_id, draft_id, platform, scheduled_at,
                        status, draft_version, content_hash, idempotency_key,
                        attempt_count, last_error_code, provider_post_id, created_at,
                        updated_at, published_at
                    ) VALUES (?, ?, ?, ?, ?, 'scheduled', ?, ?, ?, 0, NULL, NULL, ?, ?, NULL)
                    """,
                    (
                        schedule_id,
                        owner_user_id,
                        str(draft_id),
                        draft["platform"],
                        scheduled_utc.isoformat(),
                        draft["version"],
                        draft["content_hash"],
                        idempotency_key,
                        created_at,
                        created_at,
                    ),
                )
                row = connection.execute(
                    "SELECT * FROM content_publish_schedules WHERE schedule_id = ?",
                    (schedule_id,),
                ).fetchone()
        except sqlite3.IntegrityError as exc:
            raise ScheduleConflict(
                "This draft already has an active publishing schedule or this request was duplicated"
            ) from exc
        return self._record(row)

    def list_schedules(
        self, owner_user_id: str, limit: int = 50, status: str | None = None
    ) -> list[dict[str, object]]:
        query = "SELECT * FROM content_publish_schedules WHERE owner_user_id = ?"
        params: list[object] = [owner_user_id]
        if status is not None:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY scheduled_at ASC, created_at ASC LIMIT ?"
        params.append(limit)
        with self.tasks._connection() as connection:
            rows = connection.execute(query, params).fetchall()
        return [self._record(row) for row in rows]

    def get(self, owner_user_id: str, schedule_id: UUID) -> dict[str, object] | None:
        with self.tasks._connection() as connection:
            row = connection.execute(
                "SELECT * FROM content_publish_schedules WHERE schedule_id = ? AND owner_user_id = ?",
                (str(schedule_id), owner_user_id),
            ).fetchone()
        return self._record(row) if row is not None else None

    def cancel(self, owner_user_id: str, schedule_id: UUID) -> dict[str, object] | None:
        now = self._now()
        with self.tasks._connection() as connection:
            row = connection.execute(
                "SELECT * FROM content_publish_schedules WHERE schedule_id = ? AND owner_user_id = ?",
                (str(schedule_id), owner_user_id),
            ).fetchone()
            if row is None:
                return None
            if row["status"] != "scheduled":
                raise ScheduleConflict("Only a pending schedule can be cancelled")
            connection.execute(
                """
                UPDATE content_publish_schedules
                SET status = 'cancelled', updated_at = ?
                WHERE schedule_id = ? AND owner_user_id = ? AND status = 'scheduled'
                """,
                (now, str(schedule_id), owner_user_id),
            )
            updated = connection.execute(
                "SELECT * FROM content_publish_schedules WHERE schedule_id = ? AND owner_user_id = ?",
                (str(schedule_id), owner_user_id),
            ).fetchone()
        return self._record(updated) if updated is not None else None
