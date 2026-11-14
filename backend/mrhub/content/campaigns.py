"""Owner-scoped Instagram + Telegram campaign linkage and atomic scheduling."""
from __future__ import annotations

import hashlib
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from mrhub.content.repository import ContentDraftRepository


class CampaignConflict(ValueError):
    """Raised when campaign drafts or scheduling state are invalid."""


class ContentCampaignRepository:
    """Link two existing approved drafts without introducing another scheduler."""

    def __init__(self, database_path: Path) -> None:
        self.drafts = ContentDraftRepository(database_path)
        self.tasks = self.drafts.tasks

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()

    @staticmethod
    def _campaign_status(row, schedules: list[sqlite3.Row]) -> str:
        if row["status"] == "cancelled":
            return "cancelled"
        if not schedules:
            return row["status"]
        statuses = [item["status"] for item in schedules]
        if len(statuses) == 2 and all(value == "published" for value in statuses):
            return "published"
        if any(value == "published" for value in statuses) and any(
            value in {"failed", "unknown_outcome", "cancelled"} for value in statuses
        ):
            return "partial"
        if "unknown_outcome" in statuses:
            return "unknown_outcome"
        if all(value == "cancelled" for value in statuses):
            return "cancelled"
        if all(value in {"failed", "cancelled"} for value in statuses):
            return "failed"
        if any(value in {"scheduled", "publishing"} for value in statuses):
            return "scheduled"
        if "failed" in statuses:
            return "failed"
        return row["status"]

    def _record(self, row, connection) -> dict[str, object]:
        schedules = connection.execute(
            """SELECT schedule_id, draft_id, platform, scheduled_at, status,
                      provider_post_id, published_at, last_error_code
               FROM content_publish_schedules
               WHERE owner_user_id = ? AND draft_id IN (?, ?)
               ORDER BY platform""",
            (row["owner_user_id"], row["instagram_draft_id"], row["telegram_draft_id"]),
        ).fetchall()
        return {
            "campaign_id": row["campaign_id"],
            "title": row["title"],
            "instagram_draft_id": row["instagram_draft_id"],
            "telegram_draft_id": row["telegram_draft_id"],
            "status": self._campaign_status(row, schedules),
            "schedules": [dict(item) for item in schedules],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def create(
        self, owner_user_id: str, title: str, instagram_draft_id: UUID,
        telegram_draft_id: UUID,
    ) -> dict[str, object]:
        title = title.strip()
        if not 1 <= len(title) <= 200:
            raise CampaignConflict("Campaign title must contain 1 to 200 characters")
        if instagram_draft_id == telegram_draft_id:
            raise CampaignConflict("Instagram and Telegram drafts must be different")
        with self.tasks._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            drafts = connection.execute(
                """SELECT draft_id, owner_user_id, platform, content_type, status, media_asset_id
                   FROM content_drafts
                   WHERE owner_user_id = ? AND draft_id IN (?, ?)""",
                (owner_user_id, str(instagram_draft_id), str(telegram_draft_id)),
            ).fetchall()
            by_id = {item["draft_id"]: item for item in drafts}
            instagram = by_id.get(str(instagram_draft_id))
            telegram = by_id.get(str(telegram_draft_id))
            if instagram is None or telegram is None:
                raise KeyError("One or both content drafts were not found")
            if instagram["platform"] != "instagram" or instagram["content_type"] != "reel":
                raise CampaignConflict("Instagram campaign item must be an Instagram Reel draft")
            if telegram["platform"] != "telegram":
                raise CampaignConflict("Companion lesson must be a Telegram draft")
            linked = connection.execute(
                """SELECT 1 FROM content_campaigns
                   WHERE owner_user_id = ?
                     AND (instagram_draft_id IN (?, ?) OR telegram_draft_id IN (?, ?))
                   LIMIT 1""",
                (
                    owner_user_id,
                    str(instagram_draft_id),
                    str(telegram_draft_id),
                    str(instagram_draft_id),
                    str(telegram_draft_id),
                ),
            ).fetchone()
            if linked is not None:
                raise CampaignConflict("A campaign draft cannot be reused in another campaign")
            prior_schedule = connection.execute(
                """SELECT 1 FROM content_publish_schedules
                   WHERE owner_user_id = ? AND draft_id IN (?, ?)
                   LIMIT 1""",
                (owner_user_id, str(instagram_draft_id), str(telegram_draft_id)),
            ).fetchone()
            if prior_schedule is not None:
                raise CampaignConflict("Campaign drafts must not have prior publishing schedules")
            if instagram["status"] != "approved" or telegram["status"] != "approved":
                raise CampaignConflict("Both campaign drafts must be approved before linking")
            if not instagram["media_asset_id"]:
                raise CampaignConflict("Instagram Reel must have a verified rendered MP4 asset")
            asset = connection.execute(
                """SELECT media_type, processing_status, processing_profile
                   FROM content_assets WHERE asset_id = ? AND owner_user_id = ?""",
                (instagram["media_asset_id"], owner_user_id),
            ).fetchone()
            if (
                asset is None or asset["media_type"] != "video/mp4"
                or asset["processing_status"] != "processed"
                or asset["processing_profile"] != "video_render_cut_v1"
            ):
                raise CampaignConflict("Instagram Reel requires a processed video_render_cut_v1 MP4")
            campaign_id = str(uuid4())
            now = self._now()
            try:
                connection.execute(
                    """INSERT INTO content_campaigns (
                        campaign_id, owner_user_id, title, instagram_draft_id,
                        telegram_draft_id, status, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, 'draft', ?, ?)""",
                    (campaign_id, owner_user_id, title, str(instagram_draft_id),
                     str(telegram_draft_id), now, now),
                )
            except sqlite3.IntegrityError as exc:
                raise CampaignConflict("These drafts are already linked to a campaign") from exc
            row = connection.execute(
                "SELECT * FROM content_campaigns WHERE campaign_id = ? AND owner_user_id = ?",
                (campaign_id, owner_user_id),
            ).fetchone()
            return self._record(row, connection)

    def schedule(
        self, owner_user_id: str, campaign_id: UUID, scheduled_at: datetime,
    ) -> dict[str, object] | None:
        if scheduled_at.tzinfo is None or scheduled_at.utcoffset() is None:
            raise CampaignConflict("scheduled_at must include a timezone")
        scheduled_utc = scheduled_at.astimezone(UTC)
        now = datetime.now(UTC)
        if scheduled_utc <= now:
            raise CampaignConflict("scheduled_at must be in the future")
        now_text = now.isoformat()
        with self.tasks._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            campaign = connection.execute(
                "SELECT * FROM content_campaigns WHERE campaign_id = ? AND owner_user_id = ?",
                (str(campaign_id), owner_user_id),
            ).fetchone()
            if campaign is None:
                return None
            if campaign["status"] != "draft":
                raise CampaignConflict("Only an unscheduled campaign can be scheduled")
            draft_ids = [campaign["instagram_draft_id"], campaign["telegram_draft_id"]]
            drafts = connection.execute(
                """SELECT * FROM content_drafts
                   WHERE owner_user_id = ? AND draft_id IN (?, ?)""",
                (owner_user_id, *draft_ids),
            ).fetchall()
            by_id = {item["draft_id"]: item for item in drafts}
            if len(by_id) != 2 or any(item["status"] != "approved" for item in drafts):
                raise CampaignConflict("Both campaign drafts must remain approved")
            instagram = by_id[campaign["instagram_draft_id"]]
            if not instagram["media_asset_id"]:
                raise CampaignConflict("Instagram Reel must have a verified rendered MP4 asset")
            asset = connection.execute(
                """SELECT media_type, processing_status, processing_profile
                   FROM content_assets WHERE asset_id = ? AND owner_user_id = ?""",
                (instagram["media_asset_id"], owner_user_id),
            ).fetchone()
            if (
                asset is None or asset["media_type"] != "video/mp4"
                or asset["processing_status"] != "processed"
                or asset["processing_profile"] != "video_render_cut_v1"
            ):
                raise CampaignConflict("Instagram Reel render is no longer publishable")
            for draft_id in draft_ids:
                draft = by_id[draft_id]
                existing = connection.execute(
                    """SELECT status FROM content_publish_schedules
                       WHERE owner_user_id = ? AND draft_id = ?
                       LIMIT 1""",
                    (owner_user_id, draft_id),
                ).fetchone()
                if existing is not None:
                    raise CampaignConflict("A campaign draft already has publishing history")
                schedule_id = str(uuid4())
                idempotency_key = hashlib.sha256(
                    f"{owner_user_id}:{campaign_id}:{draft_id}:{draft['version']}:{scheduled_utc.isoformat()}".encode()
                ).hexdigest()
                connection.execute(
                    """INSERT INTO content_publish_schedules (
                        schedule_id, owner_user_id, draft_id, platform, scheduled_at,
                        status, draft_version, content_hash, idempotency_key,
                        attempt_count, last_error_code, provider_post_id, created_at,
                        updated_at, published_at
                    ) VALUES (?, ?, ?, ?, ?, 'scheduled', ?, ?, ?, 0, NULL, NULL, ?, ?, NULL)""",
                    (schedule_id, owner_user_id, draft_id, draft["platform"],
                     scheduled_utc.isoformat(), draft["version"], draft["content_hash"],
                     idempotency_key, now_text, now_text),
                )
            connection.execute(
                "UPDATE content_campaigns SET status = 'scheduled', updated_at = ? "
                "WHERE campaign_id = ? AND owner_user_id = ?",
                (now_text, str(campaign_id), owner_user_id),
            )
            updated = connection.execute(
                "SELECT * FROM content_campaigns WHERE campaign_id = ? AND owner_user_id = ?",
                (str(campaign_id), owner_user_id),
            ).fetchone()
            return self._record(updated, connection)

    def cancel(self, owner_user_id: str, campaign_id: UUID) -> dict[str, object] | None:
        now = self._now()
        with self.tasks._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            campaign = connection.execute(
                "SELECT * FROM content_campaigns WHERE campaign_id = ? AND owner_user_id = ?",
                (str(campaign_id), owner_user_id),
            ).fetchone()
            if campaign is None:
                return None
            if campaign["status"] != "scheduled":
                raise CampaignConflict("Only a scheduled campaign can be cancelled")
            schedules = connection.execute(
                """SELECT schedule_id, status FROM content_publish_schedules
                   WHERE owner_user_id = ? AND draft_id IN (?, ?)""",
                (owner_user_id, campaign["instagram_draft_id"], campaign["telegram_draft_id"]),
            ).fetchall()
            if len(schedules) != 2 or any(item["status"] != "scheduled" for item in schedules):
                raise CampaignConflict("Campaign delivery has started; it cannot be cancelled as a pair")
            connection.execute(
                """UPDATE content_publish_schedules
                   SET status = 'cancelled', updated_at = ?
                   WHERE owner_user_id = ? AND draft_id IN (?, ?) AND status = 'scheduled'""",
                (now, owner_user_id, campaign["instagram_draft_id"], campaign["telegram_draft_id"]),
            )
            connection.execute(
                "UPDATE content_campaigns SET status = 'cancelled', updated_at = ? "
                "WHERE campaign_id = ? AND owner_user_id = ?",
                (now, str(campaign_id), owner_user_id),
            )
            updated = connection.execute(
                "SELECT * FROM content_campaigns WHERE campaign_id = ? AND owner_user_id = ?",
                (str(campaign_id), owner_user_id),
            ).fetchone()
            return self._record(updated, connection)

    def get(self, owner_user_id: str, campaign_id: UUID) -> dict[str, object] | None:
        with self.tasks._connection() as connection:
            row = connection.execute(
                "SELECT * FROM content_campaigns WHERE campaign_id = ? AND owner_user_id = ?",
                (str(campaign_id), owner_user_id),
            ).fetchone()
            return self._record(row, connection) if row is not None else None

    def list(self, owner_user_id: str, limit: int = 50) -> list[dict[str, object]]:
        with self.tasks._connection() as connection:
            rows = connection.execute(
                """SELECT * FROM content_campaigns WHERE owner_user_id = ?
                   ORDER BY updated_at DESC, created_at DESC LIMIT ?""",
                (owner_user_id, limit),
            ).fetchall()
            return [self._record(row, connection) for row in rows]
