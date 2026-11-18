from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest

from mrhub.domain.tasks import TaskStatus
from mrhub.infrastructure.database import TaskRepository
from mrhub.jobs.worker import WorkerEngine
from mrhub.media.repository import MediaAssetRepository
from mrhub.video_intelligence.scene_jobs import (
    SceneJobCapacityExceeded,
    SceneJobSourceNotFound,
    SceneJobSourceNotReady,
    SceneJobUnsupportedMedia,
    VideoSceneJobConflict,
    VideoSceneJobRepository,
)
from mrhub.video_intelligence.scenes import SceneDetectionResult
from mrhub.video_intelligence.schemas import VideoTechnicalMetadata


def _setup(tmp_path: Path):
    database_path = tmp_path / "video-scene-jobs.sqlite3"
    tasks = TaskRepository(database_path)
    tasks.initialize()
    tasks.create_auth_user("owner-a", "owner-a", "salt-a", "hash-a")
    tasks.create_auth_user("owner-b", "owner-b", "salt-b", "hash-b")
    media = MediaAssetRepository(database_path)
    jobs = VideoSceneJobRepository(database_path)
    asset = media.store_upload(
        "owner-a", "sample.mp4", "video/mp4",
        b"\x00\x00\x00\x18ftypisom\x00\x00\x00\x00",
    )
    return database_path, tasks, media, jobs, asset


def test_scene_jobs_are_owner_scoped_and_idempotent(tmp_path):
    _database_path, _tasks, _media, jobs, asset = _setup(tmp_path)
    asset_id = UUID(str(asset["asset_id"]))
    accepted, created = jobs.create(
        "owner-a", asset_id, idempotency_key="scene-request-1"
    )
    replay, replay_created = jobs.create(
        "owner-a", asset_id, idempotency_key="scene-request-1"
    )

    assert created is True
    assert replay_created is False
    assert replay["job_id"] == accepted["job_id"]
    assert jobs.get("owner-a", UUID(str(accepted["job_id"])))["status"] == "queued"
    assert jobs.get("owner-b", UUID(str(accepted["job_id"]))) is None
    worker_payload = jobs.get_for_worker(UUID(str(accepted["task_id"])))
    assert worker_payload is not None
    assert worker_payload["owner_user_id"] == "owner-a"


def test_scene_job_idempotency_conflict_and_owner_asset_check(tmp_path):
    _database_path, _tasks, _media, jobs, asset = _setup(tmp_path)
    asset_id = UUID(str(asset["asset_id"]))
    jobs.create("owner-a", asset_id, idempotency_key="same-key")
    with pytest.raises(VideoSceneJobConflict):
        jobs.create(
            "owner-a", asset_id, idempotency_key="same-key",
            threshold=0.45,
        )
    with pytest.raises(SceneJobSourceNotFound):
        jobs.create("owner-b", asset_id, idempotency_key="other-owner")


def test_scene_jobs_reject_unsupported_and_unready_assets(tmp_path):
    _database_path, _tasks, media, jobs, asset = _setup(tmp_path)
    image = media.store_upload("owner-a", "poster.png", "image/png", b"image")
    with pytest.raises(SceneJobUnsupportedMedia):
        jobs.create("owner-a", UUID(str(image["asset_id"])), idempotency_key="image")
    with media.tasks._connection() as connection:
        connection.execute(
            "UPDATE content_assets SET processing_status = 'processing' WHERE asset_id = ?",
            (str(asset["asset_id"]),),
        )
    with pytest.raises(SceneJobSourceNotReady):
        jobs.create("owner-a", UUID(str(asset["asset_id"])), idempotency_key="not-ready")


def test_scene_jobs_enforce_per_owner_capacity(tmp_path, monkeypatch):
    from mrhub.video_intelligence import scene_jobs

    monkeypatch.setattr(scene_jobs, "MAX_ACTIVE_SCENE_JOBS_PER_OWNER", 1)
    _database_path, _tasks, _media, jobs, asset = _setup(tmp_path)
    asset_id = UUID(str(asset["asset_id"]))
    jobs.create("owner-a", asset_id, idempotency_key="one")
    with pytest.raises(SceneJobCapacityExceeded):
        jobs.create("owner-a", asset_id, idempotency_key="two")


def test_worker_runs_scene_detection_on_a_verified_private_snapshot(tmp_path, monkeypatch):
    from mrhub.video_intelligence import scene_worker

    _database_path, tasks, _media, jobs, asset = _setup(tmp_path)
    accepted, _ = jobs.create(
        "owner-a", UUID(str(asset["asset_id"])),
        idempotency_key="worker-scene",
        threshold=0.35,
        max_scene_changes=10,
    )
    calls = {}

    def fake_probe(path):
        calls["probe_path"] = path
        return VideoTechnicalMetadata(
            duration_seconds=4.0, width=1280, height=720,
            frame_rate=30, codec="h264", has_audio=True,
            metadata_status="available",
        )

    def fake_detect(path, *, duration_seconds, threshold, max_scene_changes):
        calls["detect_path"] = path
        calls["duration_seconds"] = duration_seconds
        calls["threshold"] = threshold
        calls["max_scene_changes"] = max_scene_changes
        return SceneDetectionResult((0.0, 2.0), truncated=False)

    monkeypatch.setattr(scene_worker, "probe_video", fake_probe)
    monkeypatch.setattr(scene_worker, "detect_scene_boundaries", fake_detect)
    completed = WorkerEngine(tasks).run_once()

    assert completed is not None and completed.status is TaskStatus.SUCCEEDED
    assert calls["probe_path"] == calls["detect_path"]
    assert calls["duration_seconds"] == 4.0
    assert calls["threshold"] == 0.35
    assert calls["max_scene_changes"] == 10
    record = jobs.get("owner-a", UUID(str(accepted["job_id"])))
    assert record is not None
    assert record["result"] == {
        "scene_start_times": [0.0, 2.0],
        "scene_count": 2,
        "truncated": False,
    }
    with tasks._connection() as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM media_asset_analysis_leases WHERE task_id = ?",
            (accepted["task_id"],),
        ).fetchone()[0] == 0


def test_worker_fails_closed_when_source_is_deleted(tmp_path):
    _database_path, tasks, media, jobs, asset = _setup(tmp_path)
    accepted, _ = jobs.create(
        "owner-a", UUID(str(asset["asset_id"])), idempotency_key="deleted-source"
    )
    media.delete("owner-a", UUID(str(asset["asset_id"])))
    completed = WorkerEngine(tasks).run_once()

    assert completed is not None and completed.status is TaskStatus.FAILED
    record = jobs.get("owner-a", UUID(str(accepted["job_id"])))
    assert record is not None
    assert record["error_code"] == "video_scene_source_removed"


def test_worker_failure_codes_are_sanitized(tmp_path, monkeypatch):
    from mrhub.video_intelligence import scene_worker
    from mrhub.video_intelligence.scenes import SceneDetectionError

    _database_path, tasks, _media, jobs, asset = _setup(tmp_path)
    accepted, _ = jobs.create(
        "owner-a", UUID(str(asset["asset_id"])), idempotency_key="timeout"
    )
    monkeypatch.setattr(
        scene_worker, "probe_video",
        lambda _path: VideoTechnicalMetadata(
            duration_seconds=4.0, width=1280, height=720,
            frame_rate=30, codec="h264", has_audio=True,
            metadata_status="available",
        ),
    )
    monkeypatch.setattr(
        scene_worker, "detect_scene_boundaries",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(SceneDetectionError("detection_timeout")),
    )
    completed = WorkerEngine(tasks).run_once()
    assert completed is not None and completed.status is TaskStatus.FAILED
    record = jobs.get("owner-a", UUID(str(accepted["job_id"])))
    assert record is not None
    assert record["error_code"] == "video_scene_detection_timeout"


def test_stale_scene_worker_recovery_releases_asset_use_lock(tmp_path):
    _database_path, tasks, media, jobs, asset = _setup(tmp_path)
    accepted, _ = jobs.create(
        "owner-a", UUID(str(asset["asset_id"])), idempotency_key="stale-scene"
    )
    task_id = UUID(str(accepted["task_id"]))
    now = datetime.now(UTC)
    started_at = (now - timedelta(minutes=10)).isoformat()
    expired_at = (now - timedelta(minutes=5)).isoformat()
    with tasks._connection() as connection:
        connection.execute(
            "UPDATE tasks SET status = 'running' WHERE task_id = ?",
            (str(task_id),),
        )
        connection.execute(
            """INSERT INTO worker_executions (
                task_id, attempt_count, started_at, lease_owner,
                lease_expires_at, execution_token
            ) VALUES (?, 1, ?, 'worker-crashed', ?, 9)""",
            (str(task_id), started_at, expired_at),
        )
        connection.execute(
            """INSERT INTO media_asset_analysis_leases (
                lease_id, asset_id, owner_user_id, task_id,
                lease_owner, execution_token, created_at
            ) VALUES (?, ?, ?, ?, 'worker-crashed', 9, ?)""",
            ("stale-scene-lock", str(asset["asset_id"]), "owner-a", str(task_id), started_at),
        )

    WorkerEngine(tasks, clock=lambda: now)._recover_interrupted()
    recovered = tasks.get(task_id)
    assert recovered is not None and recovered.status is TaskStatus.FAILED
    with tasks._connection() as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM media_asset_analysis_leases WHERE task_id = ?",
            (str(task_id),),
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT status FROM idempotency_records WHERE task_id = ?",
            (str(task_id),),
        ).fetchone()["status"] == "failed"
