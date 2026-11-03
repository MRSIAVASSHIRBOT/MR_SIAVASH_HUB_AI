import base64
from datetime import UTC, datetime, timedelta
from threading import Event
from uuid import UUID

import pytest

from mrhub.infrastructure.database import TaskRepository
from mrhub.jobs.leases import WorkerLease
from mrhub.media.repository import MediaAssetRepository
from mrhub.video_intelligence.analyzer import (
    AnalyzedVideoAsset,
    VideoAssetAnalysisError,
)
from mrhub.video_intelligence.frames import ExtractedVideoFrame
from mrhub.video_intelligence.jobs import VideoAnalysisJobRepository
from mrhub.video_intelligence.scenes import SceneDetectionResult
from mrhub.video_intelligence.schemas import (
    AnalysisMode,
    VideoAnalysisRequest,
    VideoTechnicalMetadata,
)
from mrhub.video_intelligence.worker import VideoAnalysisWorkerHandler


class SuccessfulAnalyzer:
    def __init__(self, content_hash: str) -> None:
        self.content_hash = content_hash
        self.calls = []

    def analyze(self, owner_user_id, asset_id, *, duration_seconds, max_frames):
        self.calls.append((owner_user_id, asset_id, duration_seconds, max_frames))
        return AnalyzedVideoAsset(
            asset_id=asset_id,
            content_hash=self.content_hash,
            analyzed_duration_seconds=8.0,
            metadata=VideoTechnicalMetadata(
                duration_seconds=8.0,
                width=1280,
                height=720,
                frame_rate=24.0,
                codec="h264",
                has_audio=True,
                metadata_status="available",
            ),
            frames=(ExtractedVideoFrame(0.5, b"jpeg-frame"),),
            scenes=SceneDetectionResult((0.0, 3.25), truncated=False),
        )


class FailingAnalyzer:
    def analyze(self, owner_user_id, asset_id, *, duration_seconds, max_frames):
        raise VideoAssetAnalysisError("scene_detection_timeout")


def make_running_handler(tmp_path, monkeypatch, analyzer):
    monkeypatch.setenv(
        "MRH_WORKFLOW_PAYLOAD_KEY",
        base64.urlsafe_b64encode(b"v" * 32).decode("ascii"),
    )
    database_path = tmp_path / "video-worker.sqlite3"
    tasks = TaskRepository(database_path)
    tasks.initialize()
    tasks.create_auth_user("owner-a", "owner-a", "salt-a", "hash-a")

    media = MediaAssetRepository(database_path)
    asset = media.store_upload(
        "owner-a", "source.mp4", "video/mp4", b"video-worker-fixture"
    )
    asset_id = UUID(str(asset["asset_id"]))

    jobs = VideoAnalysisJobRepository(database_path)
    request = VideoAnalysisRequest(
        mode=AnalysisMode.FAITHFUL,
        source_asset_ids=[str(asset_id)],
        duration_seconds=20,
    )
    accepted, created = jobs.submit("owner-a", request, "worker-test-key")
    assert created is True
    task_id = UUID(accepted["task_id"])
    task = tasks.get(task_id)
    assert task is not None

    expires_at = (datetime.now(UTC) + timedelta(minutes=5)).isoformat()
    with tasks._connection() as connection:
        connection.execute(
            """INSERT INTO worker_executions (
                task_id, lease_owner, lease_expires_at, execution_token
            ) VALUES (?, ?, ?, ?)""",
            (str(task_id), "worker-test", expires_at, 7),
        )
    lease = WorkerLease(
        task_id=str(task_id),
        owner="worker-test",
        fencing_token=7,
        expires_at=expires_at,
    )

    handler = VideoAnalysisWorkerHandler(tasks)
    handler.analyzer = analyzer
    return tasks, media, jobs, handler, task, lease, asset_id, accepted


def test_video_analysis_worker_uses_shared_analyzer_and_releases_asset_lease(
    tmp_path, monkeypatch
):
    content_hash = "a" * 64
    analyzer = SuccessfulAnalyzer(content_hash)
    tasks, media, jobs, handler, task, lease, asset_id, accepted = make_running_handler(
        tmp_path, monkeypatch, analyzer
    )

    result = handler(task, lease=lease, lease_lost=Event())

    record = jobs.get("owner-a", UUID(accepted["analysis_id"]))
    assert result["status"] == "completed"
    assert record is not None
    assert record["status"] == "completed"
    assert record["result"]["assets"][0]["content_hash"] == content_hash
    assert record["result"]["assets"][0]["keyframe_count"] == 1
    assert analyzer.calls == [("owner-a", asset_id, 20.0, 12)]
    with tasks._connection() as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM media_asset_analysis_leases"
        ).fetchone()[0] == 0
    assert media.get("owner-a", asset_id) is not None


def test_video_analysis_worker_releases_asset_lease_after_analyzer_failure(
    tmp_path, monkeypatch
):
    tasks, media, jobs, handler, task, lease, asset_id, accepted = make_running_handler(
        tmp_path, monkeypatch, FailingAnalyzer()
    )

    with pytest.raises(ValueError, match="Video analysis execution failed"):
        handler(task, lease=lease, lease_lost=__import__("threading").Event())

    record = jobs.get("owner-a", UUID(accepted["analysis_id"]))
    assert record is not None
    assert record["status"] == "failed"
    assert record["error_code"] == "scene_detection_timeout"
    with tasks._connection() as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM media_asset_analysis_leases"
        ).fetchone()[0] == 0
    assert media.get("owner-a", asset_id) is not None
