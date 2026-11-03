"""Bounded worker handler for owner-scoped video analysis."""

from __future__ import annotations

from threading import Event
from uuid import UUID

from mrhub.domain.tasks import TaskRecord, TaskStatus
from mrhub.infrastructure.database import TaskRepository
from mrhub.jobs.leases import WorkerLease
from mrhub.media.repository import MediaAssetRepository
from mrhub.video_intelligence.frames import FrameExtractionError, extract_video_frames
from mrhub.video_intelligence.jobs import VideoAnalysisJobRepository
from mrhub.video_intelligence.scenes import SceneDetectionError, detect_scene_boundaries
from mrhub.video_intelligence.schemas import VideoAnalysisRequest
from mrhub.video_intelligence.service import probe_video


class VideoAnalysisWorkerHandler:
    """Run only bounded local analysis and persist owner-scoped technical facts."""

    def __init__(self, repository: TaskRepository) -> None:
        self.tasks = repository
        self.jobs = VideoAnalysisJobRepository(repository.database_path)
        self.media = MediaAssetRepository(repository.database_path)

    def __call__(
        self, task: TaskRecord, *, lease: WorkerLease, lease_lost: Event
    ) -> dict[str, object]:
        try:
            loaded = self.jobs.load_for_worker(task.task_id)
        except (ValueError, TypeError):
            owner = self.jobs.owner_for_task(task.task_id)
            return self._fail(task, owner, lease, "analysis_payload_unavailable")
        if loaded is None:
            owner = self.jobs.owner_for_task(task.task_id)
            return self._fail(task, owner, lease, "analysis_payload_unavailable")
        owner_user_id, analysis_id, payload = loaded
        try:
            request = VideoAnalysisRequest.model_validate(payload)
        except (ValueError, TypeError):
            return self._fail(task, owner_user_id, lease, "analysis_payload_invalid")

        if lease_lost.is_set():
            return {"analysis_id": str(analysis_id), "status": "lease_lost"}
        if not self.jobs.mark_running(task.task_id, owner_user_id, lease=lease):
            return {"analysis_id": str(analysis_id), "status": "lease_lost"}
        results: list[dict[str, object]] = []

        for asset_value in request.source_asset_ids:
            current = self.tasks.get(task.task_id)
            if lease_lost.is_set() or current is None or current.status is TaskStatus.CANCELLED:
                if current is not None and current.status is TaskStatus.CANCELLED:
                    self.jobs.finish(
                        task.task_id, owner_user_id, status="cancelled",
                        error_code="cancelled_by_owner", lease=lease,
                    )
                return {"analysis_id": str(analysis_id), "status": "cancelled_or_lease_lost"}

            try:
                asset_id = UUID(asset_value)
            except ValueError:
                return self._fail(task, owner_user_id, lease, "asset_id_invalid")
            asset = self.media.get(owner_user_id, asset_id)
            if asset is None:
                return self._fail(task, owner_user_id, lease, "asset_not_found")
            if asset["media_type"] not in {"video/mp4", "video/quicktime"}:
                return self._fail(task, owner_user_id, lease, "asset_type_unsupported")
            try:
                path = self.media.file_path(str(asset["storage_key"]))
            except ValueError:
                return self._fail(task, owner_user_id, lease, "asset_path_invalid")

            metadata = probe_video(path)
            if metadata.metadata_status != "available" or metadata.duration_seconds is None:
                return self._fail(task, owner_user_id, lease, "video_probe_failed")
            duration = min(float(metadata.duration_seconds), float(request.duration_seconds))
            if duration < 0.1:
                return self._fail(task, owner_user_id, lease, "video_duration_invalid")
            try:
                frames = extract_video_frames(path, duration_seconds=duration, max_frames=12)
                scenes = detect_scene_boundaries(path, duration_seconds=duration)
            except FrameExtractionError as exc:
                return self._fail(task, owner_user_id, lease, exc.reason_code)
            except SceneDetectionError as exc:
                return self._fail(task, owner_user_id, exc.reason_code)

            results.append({
                "asset_id": str(asset_id),
                "technical_metadata": metadata.model_dump(mode="json"),
                "analysis_window_seconds": round(duration, 3),
                "keyframe_count": len(frames),
                "keyframe_timestamps": [frame.timestamp_seconds for frame in frames],
                "scene_start_timestamps": list(scenes.scene_start_times),
                "scene_boundaries_truncated": scenes.truncated,
                "semantic_visual_analysis": "not_performed",
                "audio_analysis": (
                    "requested_but_not_performed"
                    if request.include_audio_analysis else "not_requested"
                ),
            })

        if lease_lost.is_set():
            return {"analysis_id": str(analysis_id), "status": "lease_lost"}
        result = {
            "analysis_id": str(analysis_id),
            "mode": request.mode.value,
            "analysis_level": "bounded_technical_and_temporal",
            "semantic_visual_analysis": False,
            "audio_analysis": (
                "requested_but_not_performed"
                if request.include_audio_analysis else "not_requested"
            ),
            "brand_profile_applied": False,
            "custom_changes_applied": False,
            "assets": results,
        }
        self.jobs.finish(task.task_id, owner_user_id, status="completed", result=result, lease=lease)
        return {"analysis_id": str(analysis_id), "status": "completed", "asset_count": len(results)}

    def _fail(
        self, task: TaskRecord, owner_user_id: str | None,
        lease: WorkerLease, error_code: str
    ) -> None:
        if owner_user_id is not None:
            self.jobs.finish(
                task.task_id, owner_user_id, status="failed",
                error_code=error_code, lease=lease
            )
        # Let WorkerEngine persist the matching terminal task failure. Exception
        # text is deliberately generic; the analysis row stores only the code.
        raise ValueError("Video analysis execution failed")
