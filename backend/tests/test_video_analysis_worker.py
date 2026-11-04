import base64
from datetime import UTC, datetime, timedelta
from threading import Event
from types import SimpleNamespace
from uuid import UUID

import pytest

from mrhub.infrastructure.database import TaskRepository
from mrhub.jobs.leases import WorkerLease
from mrhub.media.repository import MediaAssetBusy, MediaAssetRepository
from mrhub.video_intelligence.frames import ExtractedVideoFrame
from mrhub.video_intelligence.jobs import VideoAnalysisJobRepository
from mrhub.video_intelligence.scenes import SceneDetectionError, SceneDetectionResult
from mrhub.video_intelligence.schemas import (
    AnalysisMode,
    VideoAnalysisRequest,
    VideoTechnicalMetadata,
)
from mrhub.video_intelligence.worker import VideoAnalysisWorkerHandler


def _prepare_worker(tmp_path, monkeypatch):
    monkeypatch.setenv(
        "MRH_WORKFLOW_PAYLOAD_KEY",
        base64.urlsafe_b64encode(b"w" * 32).decode("ascii"),
    )
    database_path = tmp_path / "video-analysis-worker.sqlite3"
    tasks = TaskRepository(database_path)
    tasks.initialize()
    tasks.create_auth_user("owner-a", "owner-a", "test-salt", "test-hash")
    media = MediaAssetRepository(database_path)
    asset = media.store_upload(
        "owner-a", "worker-source.mp4", "video/mp4", b"bounded-worker-fixture"
    )
    asset_id = UUID(str(asset["asset_id"]))
    jobs = VideoAnalysisJobRepository(database_path)
    accepted, created = jobs.submit(
        "owner-a",
        VideoAnalysisRequest(
            mode=AnalysisMode.FAITHFUL,
            source_asset_ids=[str(asset_id)],
            duration_seconds=20,
        ),
        "worker-analysis-key",
    )
    assert created is True

    task_id = UUID(accepted["task_id"])
    with tasks._connection() as connection:
        connection.execute(
            "UPDATE tasks SET status = 'running' WHERE task_id = ?",
            (str(task_id),),
        )
    task = tasks.get(task_id)
    assert task is not None
    expires_at = (datetime.now(UTC) + timedelta(minutes=5)).isoformat()
    with tasks._connection() as connection:
        connection.execute(
            """INSERT INTO worker_executions (
                task_id, lease_owner, lease_expires_at, execution_token
            ) VALUES (?, ?, ?, ?)""",
            (str(task_id), "worker-test", expires_at, 4),
        )
    lease = WorkerLease(
        task_id=str(task_id),
        owner="worker-test",
        fencing_token=4,
        expires_at=expires_at,
    )
    handler = VideoAnalysisWorkerHandler(tasks)
    monkeypatch.setattr(
        "mrhub.video_intelligence.worker.get_settings",
        lambda: SimpleNamespace(
            local_vision_enabled=False,
            local_vision_model=None,
            local_inference_base_url="http://127.0.0.1:11434",
            local_vision_timeout_seconds=3.0,
        ),
    )
    monkeypatch.setattr(
        "mrhub.video_intelligence.analyzer.probe_video",
        lambda _path: VideoTechnicalMetadata(
            duration_seconds=8.0,
            width=1280,
            height=720,
            frame_rate=24.0,
            codec="h264",
            has_audio=True,
            metadata_status="available",
        ),
    )
    monkeypatch.setattr(
        "mrhub.video_intelligence.analyzer.extract_video_frames",
        lambda _path, **_kwargs: [
            ExtractedVideoFrame(timestamp_seconds=0.5, jpeg_bytes=b"jpeg-frame")
        ],
    )
    monkeypatch.setattr(
        "mrhub.video_intelligence.analyzer.detect_scene_boundaries",
        lambda _path, **_kwargs: SceneDetectionResult(
            scene_start_times=(0.0, 3.0), truncated=False
        ),
    )
    return tasks, media, jobs, handler, task, lease, asset_id, accepted


def test_worker_holds_asset_lock_through_semantic_analysis_and_releases_it(tmp_path, monkeypatch):
    tasks, media, jobs, handler, task, lease, asset_id, accepted = _prepare_worker(
        tmp_path, monkeypatch
    )
    observations = []

    def inspect_under_lock(frames, **_kwargs):
        assert len(frames) == 1
        with pytest.raises(MediaAssetBusy, match="video analysis"):
            media.delete("owner-a", asset_id)
        observations.append("delete_blocked_during_vision")
        return {"status": "not_configured", "frames": []}

    monkeypatch.setattr(
        "mrhub.video_intelligence.worker.analyze_sampled_frames",
        inspect_under_lock,
    )

    result = handler(task, lease=lease, lease_lost=Event())

    assert result["status"] == "completed"
    assert observations == ["delete_blocked_during_vision"]
    analysis = jobs.get("owner-a", UUID(accepted["analysis_id"]))
    assert analysis is not None and analysis["status"] == "completed"
    with tasks._connection() as connection:
        assert (
            connection.execute("SELECT COUNT(*) FROM media_asset_analysis_leases").fetchone()[0]
            == 0
        )
    assert media.delete("owner-a", asset_id) is not None
    assert media.cleanup_pending_files("owner-a") == 0


def test_worker_releases_asset_lock_when_scene_detection_fails(tmp_path, monkeypatch):
    tasks, media, _jobs, handler, task, lease, asset_id, _accepted = _prepare_worker(
        tmp_path, monkeypatch
    )

    def fail_scene_detection(_path, **_kwargs):
        raise SceneDetectionError("detection_timeout")

    monkeypatch.setattr(
        "mrhub.video_intelligence.analyzer.detect_scene_boundaries",
        fail_scene_detection,
    )

    with pytest.raises(ValueError, match="Video analysis execution failed"):
        handler(task, lease=lease, lease_lost=Event())

    with tasks._connection() as connection:
        assert (
            connection.execute("SELECT COUNT(*) FROM media_asset_analysis_leases").fetchone()[0]
            == 0
        )
    assert media.delete("owner-a", asset_id) is not None
    assert media.cleanup_pending_files("owner-a") == 0
