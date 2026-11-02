"""Pull-driven dispatcher for approved, durable content schedules.

No platform adapter is enabled by default. Ambiguous provider outcomes are never retried
automatically because the remote service may already have accepted the post.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Protocol

from mrhub.content.scheduling import ContentScheduleRepository
from mrhub.security.audit import AuditLogger


@dataclass(frozen=True)
class PublishReceipt:
    provider_post_id: str | None = None


class PublishAdapter(Protocol):
    """Provider adapter must document whether failures are known not to have published."""

    def publish(self, draft: dict[str, object], *, idempotency_key: str) -> PublishReceipt:
        """Publish an approved draft and return provider confirmation."""
        ...


class TransientPublishError(RuntimeError):
    """Provider definitively rejected the request and confirms no post was created."""


class UnknownPublishOutcome(RuntimeError):
    """Provider outcome is ambiguous; the post may already exist."""


class ContentScheduleDispatcher:
    MAX_ATTEMPTS = 3
    CLAIM_STALE_AFTER = timedelta(minutes=5)

    def __init__(
        self,
        database_path: Path,
        adapters: dict[str, PublishAdapter] | None = None,
        clock=None,
    ) -> None:
        self.repository = ContentScheduleRepository(database_path)
        self.adapters = adapters or {}
        self._clock = clock or (lambda: datetime.now(UTC))

    def _now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Dispatcher clock must be timezone-aware")
        return value.astimezone(UTC)

    def run_once(self) -> dict[str, object] | None:
        """Claim and process at most one due schedule; never runs automatically at startup."""
        now = self._now()
        now_text = now.isoformat()
        stale_before = (now - self.CLAIM_STALE_AFTER).isoformat()
        tasks = self.repository.tasks

        # A crash after sending a provider request is ambiguous. Quarantine rather than replay.
        with tasks._connection() as connection:
            connection.execute(
                """
                UPDATE content_publish_schedules
                SET status = 'unknown_outcome', last_error_code = 'worker_interrupted',
                    updated_at = ?
                WHERE status = 'publishing' AND updated_at <= ?
                """,
                (now_text, stale_before),
            )

        with tasks._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT * FROM content_publish_schedules
                WHERE status = 'scheduled'
                  AND scheduled_at <= ?
                  AND (next_attempt_at IS NULL OR next_attempt_at <= ?)
                ORDER BY COALESCE(next_attempt_at, scheduled_at), created_at
                LIMIT 1
                """,
                (now_text, now_text),
            ).fetchone()
            if row is None:
                return None
            cursor = connection.execute(
                """
                UPDATE content_publish_schedules
                SET status = 'publishing', attempt_count = attempt_count + 1,
                    updated_at = ?, last_error_code = NULL
                WHERE schedule_id = ? AND status = 'scheduled'
                """,
                (now_text, row["schedule_id"]),
            )
            if cursor.rowcount != 1:
                return None
            claimed = connection.execute(
                "SELECT * FROM content_publish_schedules WHERE schedule_id = ?",
                (row["schedule_id"],),
            ).fetchone()
            draft_row = connection.execute(
                """
                SELECT * FROM content_drafts
                WHERE draft_id = ? AND owner_user_id = ?
                """,
                (claimed["draft_id"], claimed["owner_user_id"]),
            ).fetchone()

            # Revalidate approval/version/hash immediately before any external side effect.
            if (
                draft_row is None
                or draft_row["status"] != "approved"
                or draft_row["version"] != claimed["draft_version"]
                or draft_row["content_hash"] != claimed["content_hash"]
            ):
                connection.execute(
                    """
                    UPDATE content_publish_schedules
                    SET status = 'failed', last_error_code = 'draft_approval_stale',
                        updated_at = ?
                    WHERE schedule_id = ? AND status = 'publishing'
                    """,
                    (now_text, claimed["schedule_id"]),
                )
                return {
                    "schedule_id": claimed["schedule_id"],
                    "status": "failed",
                    "reason_code": "draft_approval_stale",
                }

            draft = {
                "draft_id": draft_row["draft_id"],
                "platform": draft_row["platform"],
                "content_type": draft_row["content_type"],
                "title": draft_row["title"],
                "body": draft_row["body"],
                "hashtags": json.loads(draft_row["hashtags_json"]),
                "content_hash": draft_row["content_hash"],
                "version": draft_row["version"],
            }
            schedule_id = claimed["schedule_id"]
            idempotency_key = claimed["idempotency_key"]
            attempt_count = claimed["attempt_count"]
            platform = claimed["platform"]

        adapter = self.adapters.get(platform)
        if adapter is None:
            self._finish(
                schedule_id, "failed", "provider_not_configured", now=self._now()
            )
            return {
                "schedule_id": schedule_id,
                "status": "failed",
                "reason_code": "provider_not_configured",
            }

        try:
            receipt = adapter.publish(draft, idempotency_key=idempotency_key)
        except TransientPublishError:
            if attempt_count < self.MAX_ATTEMPTS:
                delay = min(60, 5 * (2 ** (attempt_count - 1)))
                retry_at = self._now() + timedelta(seconds=delay)
                self._finish(
                    schedule_id, "scheduled", "provider_transient",
                    now=self._now(), next_attempt_at=retry_at,
                )
                status = "scheduled"
            else:
                self._finish(
                    schedule_id, "failed", "provider_retry_exhausted", now=self._now()
                )
                status = "failed"
            return {"schedule_id": schedule_id, "status": status,
                    "reason_code": "provider_transient"}
        except UnknownPublishOutcome:
            self._finish(
                schedule_id, "unknown_outcome", "provider_outcome_unknown", now=self._now()
            )
            return {
                "schedule_id": schedule_id,
                "status": "unknown_outcome",
                "reason_code": "provider_outcome_unknown",
            }
        except Exception:
            # Unknown exceptions may occur after the remote side effect. Fail closed.
            self._finish(
                schedule_id, "unknown_outcome", "provider_outcome_unknown", now=self._now()
            )
            return {
                "schedule_id": schedule_id,
                "status": "unknown_outcome",
                "reason_code": "provider_outcome_unknown",
            }

        published_at = self._now()
        with tasks._connection() as connection:
            connection.execute(
                """
                UPDATE content_publish_schedules
                SET status = 'published', provider_post_id = ?, published_at = ?,
                    updated_at = ?, next_attempt_at = NULL, last_error_code = NULL
                WHERE schedule_id = ? AND status = 'publishing'
                """,
                (
                    receipt.provider_post_id,
                    published_at.isoformat(),
                    published_at.isoformat(),
                    schedule_id,
                ),
            )
        AuditLogger(tasks).record(
            event_type="content.schedule_published",
            outcome="success",
            subject_type="content_publish_schedule",
            subject_id=schedule_id,
            metadata={"reason_code": "provider_confirmed"},
        )
        return {"schedule_id": schedule_id, "status": "published"}

    def _finish(
        self,
        schedule_id: str,
        status: str,
        reason_code: str,
        *,
        now: datetime,
        next_attempt_at: datetime | None = None,
    ) -> None:
        with self.repository.tasks._connection() as connection:
            connection.execute(
                """
                UPDATE content_publish_schedules
                SET status = ?, last_error_code = ?, updated_at = ?, next_attempt_at = ?
                WHERE schedule_id = ? AND status = 'publishing'
                """,
                (
                    status,
                    reason_code,
                    now.isoformat(),
                    next_attempt_at.isoformat() if next_attempt_at else None,
                    schedule_id,
                ),
            )
        AuditLogger(self.repository.tasks).record(
            event_type="content.schedule_attempt_finished",
            outcome="success" if status in {"scheduled", "published"} else "failure",
            subject_type="content_publish_schedule",
            subject_id=schedule_id,
            metadata={"reason_code": reason_code},
        )
