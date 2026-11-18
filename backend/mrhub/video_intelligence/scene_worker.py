"""Worker-owned, bounded scene analysis over verified owner media snapshots."""

from __future__ import annotations

import math
import tempfile
from pathlib import Path
from threading import Event
from uuid import UUID

from mrhub.domain.tasks import TaskRecord, TaskStatus
from mrhub.infrastructure.database import TaskRepository
from mrhub.jobs.leases import WorkerLease
from mrhub.jobs.worker import TerminalWorkerError
from mrhub.media.repository import MediaAssetBusy, MediaAssetRepository
from mrhub.video_intelligence.scene_jobs import VideoSceneJobRepository
from mrhub.video_intelligence.scenes import SceneDetectionError, detect_scene_boundaries
from mrhub.video_intelligence.service import probe_video


class VideoSceneWorkerHandler:
    """Run deterministic FFmpeg cut detection under the canonical worker lease."""

    _KNOWN_SCENE_ERRORS = frozenset({
        "source_missing",
        "source_size_out_of_range",
        "source_unavailable",
        "ffmpeg_unavailable",
        "detection_timeout",
        "ffmpeg_execution_failed",
        "detection_failed",
        "scene_output_too_large",
        "scene_output_invalid",
        "scene_time_base_invalid",
        "scene_timestamp_invalid",
        "scene_timestamp_out_of_range",
        "scene_timestamps_not_monotonic",
    })

    def __init__(self, repository: TaskRepository) -> None:
        self.tasks = repository
        self.jobs = VideoSceneJobRepository(repository.database_path)
        self.media = MediaAssetRepository(repository.database_path)

    def __call__(
        self, task: TaskRecord, *, lease: WorkerLease, lease_lost: Event
    ) -> dict[str, object]:
        job = self.jobs.get_for_worker(task.task_id)
        if job is None:
            raise TerminalWorkerError("video_scene_job_missing")
        owner_user_id = str(job["owner_user_id"])
        source_value = job["source_asset_id"]
        if not isinstance(source_value, str):
            raise TerminalWorkerError("video_scene_source_removed")
        try:
            asset_id = UUID(source_value)
        except ValueError as exc:
            raise TerminalWorkerError("video_scene_source_unavailable") from exc

        asset = self.media.get(owner_user_id, asset_id)
        if asset is None:
            raise TerminalWorkerError("video_scene_source_unavailable")
        if asset["media_type"] not in {"video/mp4", "video/quicktime"}:
            raise TerminalWorkerError("video_scene_unsupported_media")
        if asset["processing_status"] not in {"stored", "processed"}:
            raise TerminalWorkerError("video_scene_source_not_ready")

        try:
            acquired = self.media.acquire_analysis_use(
                owner_user_id, asset_id, lease=lease
            )
        except MediaAssetBusy as exc:
            raise TerminalWorkerError("video_scene_asset_busy") from exc
        if not acquired:
            if lease_lost.is_set():
                return {"status": "lease_lost"}
            raise TerminalWorkerError("video_scene_asset_busy")

        try:
            if lease_lost.is_set():
                return {"status": "lease_lost"}
            current = self.tasks.get(task.task_id)
            if current is None or current.status is TaskStatus.CANCELLED:
                return {"status": "cancelled"}

            asset = self.media.get(owner_user_id, asset_id)
            if asset is None:
                raise TerminalWorkerError("video_scene_source_unavailable")
            try:
                with tempfile.TemporaryDirectory(prefix="mrhub-scene-") as directory:
                    snapshot = self.media.create_verified_snapshot(
                        asset, Path(directory) / "source.mp4"
                    )
                    metadata = probe_video(snapshot)
                    if metadata.metadata_status == "ffprobe_unavailable":
                        raise TerminalWorkerError("ffprobe_unavailable")
                    duration = metadata.duration_seconds
                    if (
                        metadata.metadata_status != "available"
                        or duration is None
                        or not math.isfinite(duration)
                    ):
                        raise TerminalWorkerError("video_scene_probe_failed")
                    if not 0.1 <= duration <= 60.0:
                        raise TerminalWorkerError("video_scene_duration_out_of_range")
                    detected = detect_scene_boundaries(
                        snapshot,
                        duration_seconds=duration,
                        threshold=float(job["threshold"]),
                        max_scene_changes=int(job["max_scene_changes"]),
                    )
            except SceneDetectionError as exc:
                code = (
                    "video_scene_" + exc.reason_code
                    if exc.reason_code in self._KNOWN_SCENE_ERRORS
                    else "video_scene_detection_failed"
                )
                raise TerminalWorkerError(code) from exc
            except (OSError, TypeError, ValueError) as exc:
                raise TerminalWorkerError("video_scene_source_integrity_failed") from exc

            if lease_lost.is_set():
                return {"status": "lease_lost"}
            current = self.tasks.get(task.task_id)
            if current is None or current.status is TaskStatus.CANCELLED:
                return {"status": "cancelled"}
            return {
                "scene_start_times": list(detected.scene_start_times),
                "scene_count": detected.scene_count,
                "truncated": detected.truncated,
            }
        finally:
            self.media.release_analysis_use(
                owner_user_id, asset_id, lease=lease
            )
