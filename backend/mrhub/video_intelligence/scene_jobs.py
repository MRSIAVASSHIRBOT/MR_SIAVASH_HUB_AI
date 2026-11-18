"""Owner-scoped, idempotent admission and status for asynchronous scene analysis."""

from __future__ import annotations

import hashlib
import json
import math
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from mrhub.domain.tasks import RiskClass, TaskRecord, TaskStatus
from mrhub.infrastructure.database import TaskRepository

MAX_ACTIVE_SCENE_JOBS_PER_OWNER = 2
MAX_ACTIVE_SCENE_JOBS_GLOBAL = 25
_SUPPORTED_VIDEO_TYPES = frozenset({"video/mp4", "video/quicktime"})
_READY_ASSET_STATES = frozenset({"stored", "processed"})


class VideoSceneJobError(RuntimeError):
    """Base error for scene-job admission and lookup."""


class VideoSceneJobConflict(VideoSceneJobError):
    """An idempotency key was reused with a different request."""


class SceneJobSourceNotFound(VideoSceneJobError):
    """The requested asset is not owned by the authenticated user."""


class SceneJobUnsupportedMedia(VideoSceneJobError):
    """Scene detection requires a supported video asset."""


class SceneJobSourceNotReady(VideoSceneJobError):
    """The source asset is not ready for bounded analysis."""


class SceneJobCapacityExceeded(VideoSceneJobError):
    """A bounded active-job limit has been reached."""


class VideoSceneJobRepository:
    """Persist scene-job admission atomically with the shared task lifecycle."""

    def __init__(self, database_path: Path) -> None:
        self.tasks = TaskRepository(database_path)
        self.tasks.initialize()

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()

    @staticmethod
    def _scope(owner_user_id: str) -> str:
        return "video-scene:" + owner_user_id

    @staticmethod
    def _record(row) -> dict[str, object]:
        result = None
        error_code = row["error_code"]
        if row["result_json"] is not None:
            try:
                decoded = json.loads(row["result_json"])
            except (TypeError, json.JSONDecodeError):
                decoded = None
            if isinstance(decoded, dict):
                result = decoded
            elif row["status"] == TaskStatus.SUCCEEDED.value:
                error_code = "result_unavailable"
        return {
            "job_id": row["job_id"],
            "task_id": row["task_id"],
            "source_asset_id": row["source_asset_id"],
            "threshold": float(row["threshold"]),
            "max_scene_changes": int(row["max_scene_changes"]),
            "status": row["status"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "result": result,
            "error_code": error_code,
        }

    def create(
        self,
        owner_user_id: str,
        source_asset_id: UUID,
        *,
        idempotency_key: str,
        threshold: float = 0.30,
        max_scene_changes: int = 24,
    ) -> tuple[dict[str, object], bool]:
        """Create one bounded job, returning an existing job for an exact replay."""
        if not owner_user_id.strip():
            raise ValueError("Owner identity is required")
        key = idempotency_key.strip()
        if not key or len(key) > 255:
            raise ValueError("Idempotency-Key must contain 1 to 255 characters")
        if not math.isfinite(threshold) or not 0.05 <= threshold <= 0.95:
            raise ValueError("threshold must be finite and between 0.05 and 0.95")
        if (
            isinstance(max_scene_changes, bool)
            or not isinstance(max_scene_changes, int)
            or not 1 <= max_scene_changes <= 24
        ):
            raise ValueError("max_scene_changes must be between 1 and 24")

        canonical = json.dumps(
            {
                "source_asset_id": str(source_asset_id),
                "threshold": round(float(threshold), 3),
                "max_scene_changes": max_scene_changes,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        request_digest = hashlib.sha256(canonical).hexdigest()
        scope = self._scope(owner_user_id)
        now = self._now()
        task = TaskRecord(
            task_type="video.scene_detection",
            status=TaskStatus.QUEUED,
            risk_class=RiskClass.LOW,
            description="Owner-requested bounded scene-boundary analysis",
        )
        job_id = str(uuid4())

        with self.tasks._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                """SELECT request_digest, task_id FROM idempotency_records
                   WHERE scope = ? AND idempotency_key = ?""",
                (scope, key),
            ).fetchone()
            if existing is not None:
                if existing["request_digest"] != request_digest or not existing["task_id"]:
                    raise VideoSceneJobConflict("Idempotency key conflicts with an earlier request")
                row = connection.execute(
                    """SELECT j.job_id, j.task_id, j.source_asset_id, j.threshold,
                              j.max_scene_changes, j.created_at, t.status, t.updated_at,
                              e.result_json, e.error_code
                       FROM video_scene_jobs AS j
                       JOIN tasks AS t ON t.task_id = j.task_id
                       LEFT JOIN worker_executions AS e ON e.task_id = j.task_id
                       WHERE j.task_id = ? AND j.owner_user_id = ?""",
                    (existing["task_id"], owner_user_id),
                ).fetchone()
                if row is None:
                    raise VideoSceneJobConflict("The idempotent scene job is unavailable")
                return self._record(row), False

            asset = connection.execute(
                """SELECT media_type, processing_status FROM content_assets
                   WHERE asset_id = ? AND owner_user_id = ?""",
                (str(source_asset_id), owner_user_id),
            ).fetchone()
            if asset is None:
                raise SceneJobSourceNotFound("Owned source video was not found")
            if asset["media_type"] not in _SUPPORTED_VIDEO_TYPES:
                raise SceneJobUnsupportedMedia("Scene analysis requires an MP4 or QuickTime asset")
            if asset["processing_status"] not in _READY_ASSET_STATES:
                raise SceneJobSourceNotReady("Source video is not ready for analysis")

            active_states = (
                TaskStatus.QUEUED.value,
                TaskStatus.RUNNING.value,
                TaskStatus.WAITING_APPROVAL.value,
            )
            owner_active = connection.execute(
                """SELECT COUNT(*) AS amount
                   FROM video_scene_jobs AS j JOIN tasks AS t ON t.task_id = j.task_id
                   WHERE j.owner_user_id = ? AND t.status IN (?, ?, ?)""",
                (owner_user_id, *active_states),
            ).fetchone()["amount"]
            if int(owner_active) >= MAX_ACTIVE_SCENE_JOBS_PER_OWNER:
                raise SceneJobCapacityExceeded("Owner scene-job capacity reached")

            global_active = connection.execute(
                """SELECT COUNT(*) AS amount
                   FROM video_scene_jobs AS j JOIN tasks AS t ON t.task_id = j.task_id
                   WHERE t.status IN (?, ?, ?)""",
                active_states,
            ).fetchone()["amount"]
            if int(global_active) >= MAX_ACTIVE_SCENE_JOBS_GLOBAL:
                raise SceneJobCapacityExceeded("Global scene-job capacity reached")

            connection.execute(
                """INSERT INTO tasks (
                    task_id, task_type, status, risk_class,
                    created_at, updated_at, description
                ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    str(task.task_id), task.task_type, task.status.value,
                    task.risk_class.value, task.created_at.isoformat(),
                    task.updated_at.isoformat(), task.description,
                ),
            )
            connection.execute(
                """INSERT INTO video_scene_jobs (
                    job_id, task_id, owner_user_id, source_asset_id,
                    threshold, max_scene_changes, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    job_id, str(task.task_id), owner_user_id, str(source_asset_id),
                    float(threshold), max_scene_changes, now,
                ),
            )
            connection.execute(
                """INSERT INTO idempotency_records (
                    scope, idempotency_key, request_digest, task_id,
                    workflow_id, status, created_at, expires_at
                ) VALUES (?, ?, ?, ?, NULL, 'accepted', ?, NULL)""",
                (scope, key, request_digest, str(task.task_id), now),
            )

        return {
            "job_id": job_id,
            "task_id": str(task.task_id),
            "source_asset_id": str(source_asset_id),
            "threshold": float(threshold),
            "max_scene_changes": max_scene_changes,
            "status": TaskStatus.QUEUED.value,
            "created_at": now,
            "updated_at": now,
            "result": None,
            "error_code": None,
        }, True

    def get(self, owner_user_id: str, job_id: UUID) -> dict[str, object] | None:
        """Return a scene job only to its owner."""
        with self.tasks._connection() as connection:
            row = connection.execute(
                """SELECT j.job_id, j.task_id, j.source_asset_id, j.threshold,
                          j.max_scene_changes, j.created_at, t.status, t.updated_at,
                          e.result_json, e.error_code
                   FROM video_scene_jobs AS j
                   JOIN tasks AS t ON t.task_id = j.task_id
                   LEFT JOIN worker_executions AS e ON e.task_id = j.task_id
                   WHERE j.job_id = ? AND j.owner_user_id = ?""",
                (str(job_id), owner_user_id),
            ).fetchone()
        return self._record(row) if row is not None else None

    def get_for_worker(self, task_id: UUID) -> dict[str, object] | None:
        """Expose private source bindings only to the trusted worker."""
        with self.tasks._connection() as connection:
            row = connection.execute(
                """SELECT job_id, task_id, owner_user_id, source_asset_id,
                          threshold, max_scene_changes
                   FROM video_scene_jobs WHERE task_id = ?""",
                (str(task_id),),
            ).fetchone()
        if row is None:
            return None
        return {
            "job_id": row["job_id"],
            "task_id": row["task_id"],
            "owner_user_id": row["owner_user_id"],
            "source_asset_id": row["source_asset_id"],
            "threshold": float(row["threshold"]),
            "max_scene_changes": int(row["max_scene_changes"]),
        }
