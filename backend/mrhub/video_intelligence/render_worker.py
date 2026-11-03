"""Lease-fenced worker for owner-scoped video timeline rendering."""

from __future__ import annotations

from threading import Event
from uuid import UUID

from OSError import OSError

from mrhub.domain.tasks import TaskRecord, TaskStatus
from mrhub.infrastructure.database import TaskRepository
from mrhub.jobs.leases import WorkerLease
from mrhub.media.repository import MediaAssetRepository
from mrhub.video_intelligence.jobs import VideoAnalysisJobRepository
from mrhub.video_intelligence.render import VideoRenderError, render_video_timeline
from mrhub.video_intelligence.render_jobs import VideoRenderJobRepository
from mrhub.video_intelligence.timeline import VideoTimeline


class VideoRenderWorkerHandler:
    """Render one completed analysis timeline using only the requesting owner's media."""

    def __init__(self, repository: TaskRepository) -> None:
        self.tasks = repository
        self.jobs = VideoRenderJobRepository(repository.database_path)
        self.analyses = VideoAnalysisJobRepository(repository.database_path)
        self.media = MediaAssetRepository(repository.database_path)

    def __call__(
        self, task: TaskRecord, *, lease: WorkerLease, lease_lost: Event
    ) -> dict[str, object]:
        loaded = self.jobs.load_for_worker(task.task_id)
        if loaded is None:
            raise ValueError("Video render request is unavailable")
        owner_user_id, render_id, analysis_id = loaded
        if lease_lost.is_set() or not self.jobs.mark_running(
            task.task_id, owner_user_id, lease=lease
        ):
            return {"render_id": str(render_id), "status": "lease_lost"}

        output_path = None
        try:
            analysis = self.analyses.get(owner_user_id, analysis_id)
            if analysis is None or analysis["status"] != "completed":
                raise ValueError("source_analysis_unavailable")
            result = analysis.get("result")
            if not isinstance(result, dict):
                raise ValueError("source_analysis_invalid")
            timeline = VideoTimeline.model_validate(result.get("timeline"))
            source_ids = {clip.source_asset_id for clip in timeline.video_track}
            if not source_ids or len(source_ids) > 125:
                raise ValueError("render_source_count_invalid")

            source_paths = {}
            for asset_value in source_ids:
                if lease_lost.is_set():
                    return {"render_id": str(render_id), "status": "lease_lost"}
                try:
                    asset_id = UUID(asset_value)
                except ValueError as exc:
                    raise ValueError("render_source_id_invalid") from exc
                asset = self.media.get(owner_user_id, asset_id)
                if asset is None:
                    raise ValueError("render_source_not_found")
                if asset["media_type"] not in {"video/mp4", "video/quicktime"}:
                    raise ValueError("render_source_type_unsupported")
                path = self.media.file_path(str(asset["storage_key"]))
                if not path.is_file():
                    raise ValueError("render_source_file_missing")
                source_paths[asset_value] = path

            if lease_lost.is_set():
                return {"render_id": str(render_id), "status": "lease_lost"}
            output_asset_id, storage_key, output_path = self.media.new_output_target()
            rendered = render_video_timeline(
                timeline=timeline,
                source_paths=source_paths,
                output_path=output_path,
            )
            if lease_lost.is_set():
                output_path.unlink(missing_ok=True)
                return {"render_id": str(render_id), "status": "lease_lost"}
            current_task = self.tasks.get(task.task_id)
            if current_task is None or current_task.status is TaskStatus.CANCELLED:
                output_path.unlink(missing_ok=True)
                self.jobs.finish(
                    task.task_id, owner_user_id, status="cancelled",
                    error_code="cancelled_during_render", lease=lease,
                )
                return {"render_id": str(render_id), "status": "cancelled"}

            # Revalidate every owner binding after rendering, before publication.
            for asset_value in source_ids:
                try:
                    asset_id = UUID(asset_value)
                except ValueError as exc:
                    raise ValueError("render_source_id_invalid") from exc
                if self.media.get(owner_user_id, asset_id) is None:
                    raise ValueError("render_source_ownership_changed")

            output = self.media.register_rendered_output(
                owner_user_id,
                output_asset_id,
                storage_key,
                rendered.output_path,
                f"render-{render_id}.mp4",
                task_id=task.task_id,
                render_id=render_id,
                lease=lease,
            )
            return {
                "render_id": str(render_id),
                "status": "completed",
                "output_asset_id": str(output["asset_id"]),
                "duration_seconds": rendered.duration_seconds,
                "width": rendered.width,
                "height": rendered.height,
                "file_size": rendered.file_size,
            }
        except VideoRenderError as exc:
            if output_path is not None:
                output_path.unlink(missing_ok=True)
            self.jobs.finish(
                task.task_id, owner_user_id, status="failed",
                error_code=exc.reason_code, lease=lease,
            )
            raise ValueError("Video render execution failed") from exc
        except (ValueError, TypeError, KeyError, OSError) as exc:
            if output_path is not None:
                output_path.unlink(missing_ok=True)
            code = str(exc)[:80] if str(exc) else "render_request_invalid"
            self.jobs.finish(
                task.task_id, owner_user_id, status="failed",
                error_code=code, lease=lease,
            )
            raise ValueError("Video render execution failed") from exc
