from pathlib import Path
from uuid import UUID

import pytest

from mrhub.domain.tasks import RiskClass, TaskRecord, TaskStatus
from mrhub.infrastructure.database import TaskRepository
from mrhub.jobs.worker import WorkerEngine
from mrhub.media.repository import MediaAssetRepository
from mrhub.video_intelligence import scenes, service
from mrhub.video_intelligence.scene_jobs import (
    MAX_ACTIVE_SCENE_JOBS_PER_OWNER,
    SceneJobCapacityExceeded,
    SceneJobSourceNotFound,
    SceneJobSourceNotReady,
    SceneJobUnsupportedMedia,
    VideoSceneJobRepository,
)
from mrhub.video_intelligence.scenes import SceneDetectionError, SceneDetectionResult
from mrhub.video_intelligence.schemas import VideoTechnicalMetadata


def _setup(tmp_path: Path):
    database_path = tmp_path / "video-scene-jobs.sqlite3"
    tasks = TaskRepository(database_path)
    tasks.initialize()
    tasks.create_auth_user("owner-a", "owner-a", "salt-a", "hash-a")
    tasks.create_auth_user("owner-b", "owner-b", "salt-b", "hash-b")
    media = MediaAssetRepository(database_path)
    jobs = VideoSceneJobRepository(database_path)
    content = b"\x00\x00\x00\x18ftypisom\x00\x00\x00\x00"
    asset = media.store_upload(
        "owner-a", "sample.mp4", "video/mp4", content
    )
    return database_path, tasks, media, jobs, asset


def _metadata(duration: float = 4.0) -> VideoTechnicalMetadata:
    return VideoTechnicalMetadata(
        duration_seconds=duration,
        width=1280,
        height=720,
        frame_rate=30,
        codec="h264",
        has_audio=True,
        metadata_status="available",
    )


def test_scene_jobs_are_owner_scoped_and_create_shared_low_risk_tasks(tmp_path):
    _database_path, tasks, _media, jobs, asset = _setup(tmp_path)

    accepted = jobs.create("owner-a", UUID(str(asset["asset_id"])))

    assert accepted["status"] == TaskStatus.QUEUED.value
    task = tasks.get(UUID(str(accepted["task_id"])))
    assert task is not None
    assert task.task_type == "video.scene_detection"
    assert task.risk_class is RiskClass.LOW

    assert jobs.get("owner-a", UUID(str(accepted["job_id"])))[
        "source_asset_id"
    ] == asset["asset_id"]
    assert jobs.get("owner-b", UUID(str(accepted["job_id"]))) is None
    worker_payload = jobs.get_for_worker(UUID(str(accepted["task_id"])))
    assert worker_payload is not None
    assert worker_payload["owner_user_id"] == "owner-a"
    assert worker_payload["source_asset_id"] == asset["asset_id"]


def test_scene_job_creation_hides_non_owned_assets(tmp_path):
    _database_path, _tasks, _media, jobs, asset = _setup(tmp_path)

    with pytest.raises(SceneJobSourceNotFound):
        jobs.create("owner-b", UUID(str(asset["asset_id"])))


def test_scene_jobs_reject_images_and_assets_that_are_not_ready(tmp_path):
    database_path, _tasks, media, jobs, _asset = _setup(tmp_path)
    image = media.store_upload("owner-a", "poster.png", "image/png", b"image")

    with pytest.raises(SceneJobUnsupportedMedia):
        jobs.create("owner-a", UUID(str(image["asset_id"])))

    with media.tasks._connection() as connection:
        connection.execute(
            "UPDATE content_assets SET processing_status = 'processing' WHERE asset_id = ?",
            (str(_asset["asset_id"]),),
        )
    with pytest.raises(SceneJobSourceNotReady):
        jobs.create("owner-a", UUID(str(_asset["asset_id"])))


def test_scene_jobs_enforce_per_owner_active_capacity(tmp_path):
    _database_path, _tasks, _media, jobs, asset = _setup(tmp_path)
    asset_id = UUID(str(asset["asset_id"]))

    for _ in range(MAX_ACTIVE_SCENE_JOBS_PER_OWNER):
        jobs.create("owner-a", asset_id)

    with pytest.raises(SceneJobCapacityExceeded):
        jobs.create("owner-a", asset_id)


def test_scene_job_source_deletion_nulls_reference_without_leaking_owner_data(tmp_path):
    _database_path, _tasks, media, jobs, asset = _setup(tmp_path)
    accepted = jobs.create("owner-a", UUID(str(asset["asset_id"])))

    deleted = media.delete("owner-a", UUID(str(asset["asset_id"])))

    assert deleted is not None
    record = jobs.get("owner-a", UUID(str(accepted["job_id"])))
    assert record is not None
    assert record["source_asset_id"] is None


def test_worker_executes_scene_job_using_only_owner_resolved_media(
    tmp_path, monkeypatch
):
    database_path, tasks, _media, jobs, asset = _setup(tmp_path)
    accepted = jobs.create("owner-a", UUID(str(asset["asset_id"])))
    calls = {}

    def fake_probe(path):
        calls["probe_path"] = path
        return _metadata()

    def fake_detect(path, *, duration_seconds, threshold, max_scene_changes):
        calls["detect_path"] = path
        calls["duration_seconds"] = duration_seconds
        calls["threshold"] = threshold
        calls["max_scene_changes"] = max_scene_changes
        return SceneDetectionResult((0.0, 2.0), truncated=False)

    monkeypatch.setattr(service, "probe_video", fake_probe)
    monkeypatch.setattr(scenes, "detect_scene_boundaries", fake_detect)

    completed = WorkerEngine(tasks).run_once()

    assert completed is not None
    assert completed.status is TaskStatus.SUCCEEDED
    assert calls["probe_path"] == calls["detect_path"]
    assert calls["duration_seconds"] == 4.0
    assert calls["threshold"] == 0.30
    assert calls["max_scene_changes"] == 24
    stored = jobs.get("owner-a", UUID(str(accepted["job_id"])))
    assert stored is not None
    assert stored["status"] == TaskStatus.SUCCEEDED.value
    assert stored["result"] == {
        "scene_start_times": [0.0, 2.0],
        "scene_count": 2,
        "truncated": False,
    }


def test_worker_fails_safely_when_scene_job_source_is_deleted(tmp_path):
    database_path, tasks, media, jobs, asset = _setup(tmp_path)
    accepted = jobs.create("owner-a", UUID(str(asset["asset_id"])))
    media.delete("owner-a", UUID(str(asset["asset_id"])))

    completed = WorkerEngine(tasks).run_once()

    assert completed is not None and completed.status is TaskStatus.FAILED
    result = WorkerEngine(tasks).get_result(UUID(str(accepted["task_id"])))
    assert result is not None
    assert result["error_code"] == "video_scene_source_removed"


def test_worker_maps_scene_detection_errors_to_sanitized_terminal_codes(
    tmp_path, monkeypatch
):
    _database_path, tasks, _media, jobs, asset = _setup(tmp_path)
    accepted = jobs.create("owner-a", UUID(str(asset["asset_id"])))
    monkeypatch.setattr(service, "probe_video", lambda _path: _metadata())

    def fail_detection(*_args, **_kwargs):
        raise SceneDetectionError("detection_timeout")

    monkeypatch.setattr(scenes, "detect_scene_boundaries", fail_detection)
    completed = WorkerEngine(tasks).run_once()

    assert completed is not None and completed.status is TaskStatus.FAILED
    result = WorkerEngine(tasks).get_result(UUID(str(accepted["task_id"])))
    assert result is not None
    assert result["error_code"] == "video_scene_detection_timeout"


def test_worker_fails_closed_for_scene_task_without_private_job_record(tmp_path):
    _database_path, tasks, _media, _jobs, _asset = _setup(tmp_path)
    task = TaskRecord(task_type="video.scene_detection")
    tasks.create(task)

    completed = WorkerEngine(tasks).run_once()

    assert completed is not None and completed.status is TaskStatus.FAILED
    result = WorkerEngine(tasks).get_result(task.task_id)
    assert result is not None
    assert result["error_code"] == "video_scene_job_missing"
