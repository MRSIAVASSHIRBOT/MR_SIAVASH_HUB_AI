"""Durable owner-scoped video-render job persistence."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from mrhub.domain.tasks import RiskClass, TaskRecord
from mrhub.infrastructure.database import TaskRepository
from mrhub.jobs.leases import WorkerLease
from mrhub.video_intelligence.jobs import VideoAnalysisJobRepository
from mrhub.video_intelligence.render_snapshot_repository import VideoRenderSnapshotRepository
from mrhub.video_intelligence.timeline import VideoTimeline


class VideoRenderConflict(ValueError):
    """Raised when an idempotency key is reused for a different render request."""


class VideoRenderJobRepository:
    """Persist render requests as durable tasks and expose owner-scoped status."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self.tasks = TaskRepository(database_path)
        self.tasks.initialize()

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()

    @staticmethod
    def _scope(owner_user_id: str) -> str:
        return f"video-render:{owner_user_id}"

    def submit(
        self,
        owner_user_id: str,
        analysis_id: UUID,
        idempotency_key: str,
        *,
        snapshot_id: UUID | None = None,
    ) -> tuple[dict[str, object], bool]:
        key = idempotency_key.strip()
        if not key or len(key) > 255:
            raise ValueError("Idempotency-Key must contain 1 to 255 characters")
        analysis = VideoAnalysisJobRepository(self.database_path).get(
            owner_user_id, analysis_id
        )
        if analysis is None:
            raise LookupError("analysis_not_found")
        if analysis["status"] != "completed" or not isinstance(analysis.get("result"), dict):
            raise ValueError("analysis_not_completed")
        if snapshot_id is not None:
            snapshot = VideoRenderSnapshotRepository(self.database_path).get(
                owner_user_id, snapshot_id
            )
            if snapshot is None or snapshot.analysis_id != analysis_id:
                raise LookupError("render_snapshot_not_found")
            timeline = snapshot.validated_timeline()
            source_ids = {clip.source_asset_id for clip in timeline.video_track}
            assets = analysis["result"].get("assets")
            if not isinstance(assets, list):
                raise ValueError("analysis_assets_unavailable")
            allowed_asset_ids = {
                str(item["asset_id"])
                for item in assets
                if isinstance(item, dict) and item.get("asset_id")
            }
            if not source_ids or not source_ids.issubset(allowed_asset_ids):
                raise ValueError("render_snapshot_source_mismatch")
            digest = snapshot.idempotency_digest()
        else:
            try:
                timeline = VideoTimeline.model_validate(analysis["result"].get("timeline"))
            except (TypeError, ValueError) as exc:
                raise ValueError("analysis_timeline_unavailable") from exc
            digest = hashlib.sha256(
                json.dumps(
                    {"analysis_id": str(analysis_id), "timeline": timeline.model_dump(mode="json")},
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()
        render_id = uuid4()
        output_asset_id = uuid4()
        output_storage_key = f"{output_asset_id}.mp4"
        task = TaskRecord(
            task_type="video.render",
            risk_class=RiskClass.LOW,
            description="Owner-requested bounded video timeline render",
        )
        now = self._now()
        scope = self._scope(owner_user_id)
        with self.tasks._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT request_digest, task_id FROM idempotency_records "
                "WHERE scope = ? AND idempotency_key = ?",
                (scope, key),
            ).fetchone()
            if existing is not None:
                if existing["request_digest"] != digest or not existing["task_id"]:
                    raise VideoRenderConflict("Idempotency key conflicts with an earlier render")
                row = connection.execute(
                    """SELECT render_id, task_id, status, output_asset_id, created_at
                       FROM video_render_runs
                       WHERE task_id = ? AND owner_user_id = ?""",
                    (existing["task_id"], owner_user_id),
                ).fetchone()
                if row is None:
                    raise VideoRenderConflict("Existing render is unavailable")
                return self._record(row), False

            connection.execute(
                """INSERT INTO tasks (
                    task_id, task_type, status, risk_class, created_at, updated_at, description
                ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    str(task.task_id), task.task_type, task.status.value,
                    task.risk_class.value, task.created_at.isoformat(),
                    task.updated_at.isoformat(), task.description,
                ),
            )
            connection.execute(
                """INSERT INTO video_render_runs (
                    render_id, task_id, owner_user_id, analysis_id, status,
                    output_asset_id, output_storage_key, error_code, created_at, updated_at,
                    snapshot_id
                ) VALUES (?, ?, ?, ?, 'accepted', NULL, ?, NULL, ?, ?, ?)""",
                (
                    str(render_id), str(task.task_id), owner_user_id, str(analysis_id),
                    output_storage_key, now, now,
                    str(snapshot_id) if snapshot_id is not None else None,
                ),
            )
            connection.execute(
                """INSERT INTO idempotency_records (
                    scope, idempotency_key, request_digest, task_id,
                    workflow_id, status, created_at, expires_at
                ) VALUES (?, ?, ?, ?, NULL, 'accepted', ?, NULL)""",
                (scope, key, digest, str(task.task_id), now),
            )
        return {
            "render_id": str(render_id),
            "task_id": str(task.task_id),
            "analysis_id": str(analysis_id),
            "status": "accepted",
            "created_at": now,
        }, True

    @staticmethod
    def _record(row: sqlite3.Row) -> dict[str, object]:
        return {
            "render_id": row["render_id"],
            "task_id": row["task_id"],
            "status": row["status"],
            "output_asset_id": row["output_asset_id"],
            "created_at": row["created_at"],
        }

    def get(self, owner_user_id: str, render_id: UUID) -> dict[str, object] | None:
        with self.tasks._connection() as connection:
            row = connection.execute(
                """SELECT render_id, task_id, status, output_asset_id,
                          error_code, created_at, updated_at
                   FROM video_render_runs
                   WHERE render_id = ? AND owner_user_id = ?""",
                (str(render_id), owner_user_id),
            ).fetchone()
        if row is None:
            return None
        return {
            "render_id": row["render_id"],
            "status": row["status"],
            "output_asset_id": row["output_asset_id"],
            "error_code": row["error_code"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def cancel(
        self, owner_user_id: str, render_id: UUID
    ) -> dict[str, object] | None:
        """Cancel queued work atomically or signal a running leased worker."""
        now = self._now()
        with self.tasks._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """SELECT r.render_id, r.task_id, r.status, t.status AS task_status
                   FROM video_render_runs AS r
                   JOIN tasks AS t ON t.task_id = r.task_id
                   WHERE r.render_id = ? AND r.owner_user_id = ?""",
                (str(render_id), owner_user_id),
            ).fetchone()
            if row is None:
                return None

            render_status = str(row["status"])
            task_status = str(row["task_status"])
            if render_status in {"completed", "failed", "cancelled"}:
                return {
                    "render_id": str(render_id),
                    "status": render_status,
                    "cancellation_requested": False,
                }

            if task_status == "queued" and render_status == "accepted":
                connection.execute(
                    """UPDATE tasks SET status = 'cancelled', updated_at = ?
                       WHERE task_id = ? AND status = 'queued'""",
                    (now, row["task_id"]),
                )
                connection.execute(
                    """UPDATE video_render_runs
                       SET status = 'cancelled', error_code = 'cancelled_before_execution',
                           updated_at = ?
                       WHERE render_id = ? AND owner_user_id = ? AND status = 'accepted'""",
                    (now, str(render_id), owner_user_id),
                )
                connection.execute(
                    """UPDATE idempotency_records SET status = 'failed'
                       WHERE scope = ? AND task_id = ? AND status = 'accepted'""",
                    (self._scope(owner_user_id), row["task_id"]),
                )
                return {
                    "render_id": str(render_id),
                    "status": "cancelled",
                    "cancellation_requested": False,
                }

            if task_status == "cancelled" and render_status in {"accepted", "running"}:
                return {
                    "render_id": str(render_id),
                    "status": render_status,
                    "cancellation_requested": True,
                }

            if task_status == "running" and render_status in {"accepted", "running"}:
                cursor = connection.execute(
                    """UPDATE tasks SET status = 'cancelled', updated_at = ?
                       WHERE task_id = ? AND status = 'running'""",
                    (now, row["task_id"]),
                )
                if cursor.rowcount == 1:
                    return {
                        "render_id": str(render_id),
                        "status": render_status,
                        "cancellation_requested": True,
                    }
                latest = connection.execute(
                    """SELECT r.status FROM video_render_runs AS r
                       WHERE r.render_id = ? AND r.owner_user_id = ?""",
                    (str(render_id), owner_user_id),
                ).fetchone()
                return {
                    "render_id": str(render_id),
                    "status": str(latest["status"]) if latest is not None else render_status,
                    "cancellation_requested": False,
                }

            return {
                "render_id": str(render_id),
                "status": render_status,
                "cancellation_requested": False,
            }

    def load_for_worker(
        self, task_id: UUID
    ) -> tuple[str, UUID, UUID, str, UUID | None] | None:
        with self.tasks._connection() as connection:
            row = connection.execute(
                """SELECT render_id, owner_user_id, analysis_id, output_storage_key,
                          snapshot_id
                   FROM video_render_runs WHERE task_id = ?""",
                (str(task_id),),
            ).fetchone()
        if row is None:
            return None
        return (
            str(row["owner_user_id"]),
            UUID(row["render_id"]),
            UUID(row["analysis_id"]),
            str(row["output_storage_key"]),
            UUID(row["snapshot_id"]) if row["snapshot_id"] is not None else None,
        )

    def owner_for_task(self, task_id: UUID) -> str | None:
        with self.tasks._connection() as connection:
            row = connection.execute(
                "SELECT owner_user_id FROM video_render_runs WHERE task_id = ?",
                (str(task_id),),
            ).fetchone()
        return str(row["owner_user_id"]) if row is not None else None

    def mark_running(
        self, task_id: UUID, owner_user_id: str, *, lease: WorkerLease
    ) -> bool:
        if lease.task_id != str(task_id):
            raise ValueError("Worker lease does not belong to this render task")
        now = self._now()
        with self.tasks._connection() as connection:
            cursor = connection.execute(
                """UPDATE video_render_runs SET status = 'running', updated_at = ?
                   WHERE task_id = ? AND owner_user_id = ? AND status = 'accepted'
                     AND EXISTS (
                       SELECT 1 FROM worker_executions AS e
                       WHERE e.task_id = ? AND e.lease_owner = ?
                         AND e.execution_token = ? AND e.lease_expires_at > ?
                     )""",
                (now, str(task_id), owner_user_id, str(task_id),
                 lease.owner, lease.fencing_token, now),
            )
        return cursor.rowcount == 1

    def finish(
        self, task_id: UUID, owner_user_id: str, *, status: str,
        lease: WorkerLease, output_asset_id: str | None = None,
        error_code: str | None = None,
    ) -> bool:
        if status not in {"completed", "failed", "cancelled"}:
            raise ValueError("Invalid terminal video-render status")
        if lease.task_id != str(task_id):
            raise ValueError("Worker lease does not belong to this render task")
        now = self._now()
        with self.tasks._connection() as connection:
            cursor = connection.execute(
                """UPDATE video_render_runs
                   SET status = ?, output_asset_id = ?, error_code = ?, updated_at = ?
                   WHERE task_id = ? AND owner_user_id = ?
                     AND EXISTS (
                       SELECT 1 FROM worker_executions AS e
                       WHERE e.task_id = ? AND e.lease_owner = ?
                         AND e.execution_token = ? AND e.lease_expires_at > ?
                     )""",
                (status, output_asset_id, error_code[:80] if error_code else None,
                 now, str(task_id), owner_user_id, str(task_id),
                 lease.owner, lease.fencing_token, now),
            )
            if cursor.rowcount != 1:
                return False
            connection.execute(
                """UPDATE idempotency_records SET status = ?
                   WHERE scope = ? AND task_id = ?""",
                (
                    "completed" if status == "completed" else "failed",
                    self._scope(owner_user_id), str(task_id),
                ),
            )
        return True
