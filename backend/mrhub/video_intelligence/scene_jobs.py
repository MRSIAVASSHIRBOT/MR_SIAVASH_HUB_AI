"""Owner-scoped durable requests for background video scene analysis."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from mrhub.domain.tasks import RiskClass, TaskRecord, TaskStatus
from mrhub.infrastructure.database import TaskRepository

MAX_ACTIVE_SCENE_JOBS_PER_OWNER = 2
MAX_ACTIVE_SCENE_JOBS_GLOBAL = 100
_SUPPORTED_VIDEO_TYPES = frozenset({"video/mp4", "video/quicktime"})
_READY_ASSET_STATES = frozenset({"stored", "processed"})


class VideoSceneJobError(RuntimeError):
    """Base exception for safe scene-job admission and lookup failures."""


class SceneJobSourceNotFound(VideoSceneJobError):
    """The source asset is not owned by the requesting user."""


class SceneJobUnsupportedMedia(VideoSceneJobError):
    """The source asset is not a supported video type."""


class SceneJobSourceNotReady(VideoSceneJobError):
    """The source asset is still processing or has failed processing."""


class SceneJobCapacityExceeded(VideoSceneJobError):
    """A per-owner or global active-job limit has been reached."""


class VideoSceneJobRepository:
    """Persist scene jobs with owner checks and atomic task admission."""

    def __init__(self, database_path: Path) -> None:
        self.tasks = TaskRepository(database_path)
        self.tasks.initialize()

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()

    def create(
        self,
        owner_user_id: str,
        source_asset_id: UUID,
        *,
        threshold: float = 0.30,
        max_scene_changes: int = 24,
    ) -> dict[str, object]:
        """Create the task and its private job payload in a single transaction."""
        if not 0.05 <= threshold <= 0.95:
            raise ValueError("threshold must be between 0.05 and 0.95")
        if (
            isinstance(max_scene_changes, bool)
            or not isinstance(max_scene_changes, int)
            or not 1 <= max_scene_changes <= 24
        ):
            raise ValueError("max_scene_changes must be between 1 and 24")

        task = TaskRecord(
            task_type="video.scene_detection",
            status=TaskStatus.QUEUED,
            risk_class=RiskClass.LOW,
            description="Detect scene boundaries for an owned video asset",
        )
        job_id = str(uuid4())
        created_at = self._now()

        with self.tasks._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            asset = connection.execute(
                """
                SELECT media_type, processing_status
                FROM content_assets
                WHERE asset_id = ? AND owner_user_id = ?
                """,
                (str(source_asset_id), owner_user_id),
            ).fetchone()
            if asset is None:
                raise SceneJobSourceNotFound("Owned source video was not found")
            if asset["media_type"] not in _SUPPORTED_VIDEO_TYPES:
                raise SceneJobUnsupportedMedia("Scene detection requires an MP4 or QuickTime video")
            if asset["processing_status"] not in _READY_ASSET_STATES:
                raise SceneJobSourceNotReady("Source video is not ready for analysis")

            owner_active = connection.execute(
                """
                SELECT COUNT(*) AS amount
                FROM video_scene_jobs AS j
                JOIN tasks AS t ON t.task_id = j.task_id
                WHERE j.owner_user_id = ? AND t.status IN (?, ?, ?)
                """,
                (
                    owner_user_id,
                    TaskStatus.QUEUED.value,
                    TaskStatus.RUNNING.value,
                    TaskStatus.WAITING_APPROVAL.value,
                ),
            ).fetchone()["amount"]
            if owner_active >= MAX_ACTIVE_SCENE_JOBS_PER_OWNER:
                raise SceneJobCapacityExceeded("Owner scene-job capacity reached")

            global_active = connection.execute(
                """
                SELECT COUNT(*) AS amount
                FROM video_scene_jobs AS j
                JOIN tasks AS t ON t.task_id = j.task_id
                WHERE t.status IN (?, ?, ?)
                """,
                (
                    TaskStatus.QUEUED.value,
                    TaskStatus.RUNNING.value,
                    TaskStatus.WAITING_APPROVAL.value,
                ),
            ).fetchone()["amount"]
            if global_active >= MAX_ACTIVE_SCENE_JOBS_GLOBAL:
                raise SceneJobCapacityExceeded("Global scene-job capacity reached")

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
            connection.execute(
                """
                INSERT INTO video_scene_jobs (
                    job_id, task_id, owner_user_id, source_asset_id,
                    threshold, max_scene_changes, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    str(task.task_id),
                    owner_user_id,
                    str(source_asset_id),
                    threshold,
                    max_scene_changes,
                    created_at,
                ),
            )

        return {
            "job_id": job_id,
            "task_id": str(task.task_id),
            "status": task.status.value,
            "created_at": created_at,
        }

    def get(
        self, owner_user_id: str, job_id: UUID
    ) -> dict[str, object] | None:
        """Read a job only when its authenticated owner matches."""
        with self.tasks._connection() as connection:
            row = connection.execute(
                """
                SELECT
                    j.job_id, j.task_id, j.source_asset_id, j.threshold,
                    j.max_scene_changes, j.created_at,
                    t.status, t.updated_at,
                    e.result_json, e.error_code
                FROM video_scene_jobs AS j
                JOIN tasks AS t ON t.task_id = j.task_id
                LEFT JOIN worker_executions AS e ON e.task_id = j.task_id
                WHERE j.job_id = ? AND j.owner_user_id = ?
                """,
                (str(job_id), owner_user_id),
            ).fetchone()
        if row is None:
            return None

        result: dict[str, object] | None = None
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
            "threshold": row["threshold"],
            "max_scene_changes": row["max_scene_changes"],
            "status": row["status"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "result": result,
            "error_code": error_code,
        }

    def get_for_worker(self, task_id: UUID) -> dict[str, object] | None:
        """Return private input only to the trusted worker handling this task."""
        with self.tasks._connection() as connection:
            row = connection.execute(
                """
                SELECT job_id, task_id, owner_user_id, source_asset_id,
                       threshold, max_scene_changes
                FROM video_scene_jobs
                WHERE task_id = ?
                """,
                (str(task_id),),
            ).fetchone()
        if row is None:
            return None
        return {
            "job_id": row["job_id"],
            "task_id": row["task_id"],
            "owner_user_id": row["owner_user_id"],
            "source_asset_id": row["source_asset_id"],
            "threshold": row["threshold"],
            "max_scene_changes": row["max_scene_changes"],
        }
