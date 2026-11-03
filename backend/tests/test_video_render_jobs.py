import base64
import hashlib
from datetime import UTC, datetime
from threading import Event
from types import SimpleNamespace
from uuid import UUID

from mrhub.jobs.leases import WorkerLease
from mrhub.jobs.worker import WorkerEngine
from mrhub.media.repository import MediaAssetRepository
from mrhub.video_intelligence.jobs import VideoAnalysisJobRepository
from mrhub.video_intelligence.render_jobs import VideoRenderJobRepository
from mrhub.video_intelligence.render_worker import VideoRenderWorkerHandler
from mrhub.video_intelligence.schemas import AnalysisMode, VideoAnalysisRequest


def _completed_analysis(tmp_path, monkeypatch):
    monkeypatch.setenv(
        "MRH_WORKFLOW_PAYLOAD_KEY",
        base64.urlsafe_b64encode(b"r" * 32).decode("ascii"),
    )
    repository = VideoAnalysisJobRepository(tmp_path / "render.sqlite")
    repository.tasks.create_auth_user("owner-a", "owner-a", "salt-a", "hash-a")
    repository.tasks.create_auth_user("owner-b", "owner-b", "salt-b", "hash-b")
    source_id = "2c83d1c5-1d8d-4c29-8a3d-4dd0e0b10a00"
    accepted, _ = repository.submit(
        "owner-a",
        VideoAnalysisRequest(
            mode=AnalysisMode.FAITHFUL,
            source_asset_ids=[source_id],
            duration_seconds=3,
        ),
        "analysis-key",
    )
    task_id = UUID(accepted["task_id"])
    expiry = "2099-01-01T00:00:00+00:00"
    with repository.tasks._connection() as connection:
        connection.execute(
            """INSERT INTO worker_executions (
                task_id, lease_owner, lease_expires_at, execution_token
            ) VALUES (?, ?, ?, ?)""",
            (str(task_id), "analysis-worker", expiry, 1),
        )
        connection.execute(
            "UPDATE tasks SET status = 'running' WHERE task_id = ?",
            (str(task_id),),
        )
    repository.finish(
        task_id,
        "owner-a",
        status="completed",
        result={
            "timeline": {
                "schema_version": "1.0",
                "output_aspect_ratio": "16:9",
                "requested_duration_seconds": 3,
                "actual_duration_seconds": 3.0,
                "duration_shortfall_seconds": 0.0,
                "video_track": [
                    {
                        "clip_id": "clip-001",
                        "source_asset_id": source_id,
                        "source_scene_index": 0,
                        "source_start_seconds": 0.0,
                        "source_end_seconds": 3.0,
                        "timeline_start_seconds": 0.0,
                        "timeline_end_seconds": 3.0,
                        "transition_in": "none",
                    }
                ],
                "audio_analysis_status": "not_requested",
                "audio_render_status": "not_implemented",
                "timeline_status": "validated_cut_only",
                "render_status": "not_implemented",
            }
        },
        lease=WorkerLease(
            task_id=str(task_id),
            owner="analysis-worker",
            fencing_token=1,
            expires_at=expiry,
        ),
    )
    return repository, UUID(accepted["analysis_id"])


def test_render_submission_is_owner_scoped_and_idempotent(tmp_path, monkeypatch):
    _, analysis_id = _completed_analysis(tmp_path, monkeypatch)
    jobs = VideoRenderJobRepository(tmp_path / "render.sqlite")

    accepted, created = jobs.submit("owner-a", analysis_id, "render-key")
    assert created is True
    assert accepted["status"] == "accepted"
    with jobs.tasks._connection() as connection:
        reserved = connection.execute(
            "SELECT output_storage_key FROM video_render_runs WHERE render_id = ?",
            (accepted["render_id"],),
        ).fetchone()
    assert reserved is not None
    assert reserved["output_storage_key"].endswith(".mp4")
    assert UUID(reserved["output_storage_key"][:-4])

    replay, replay_created = jobs.submit("owner-a", analysis_id, "render-key")
    assert replay_created is False
    assert replay["render_id"] == accepted["render_id"]

    assert jobs.get("owner-b", UUID(accepted["render_id"])) is None

    try:
        jobs.submit("owner-b", analysis_id, "foreign-render-key")
    except LookupError as exc:
        assert str(exc) == "analysis_not_found"
    else:
        raise AssertionError("A different owner must not render this analysis")


def test_render_output_registration_completes_job_atomically(tmp_path, monkeypatch):
    analysis_repository, analysis_id = _completed_analysis(tmp_path, monkeypatch)
    jobs = VideoRenderJobRepository(tmp_path / "render.sqlite")
    media = MediaAssetRepository(tmp_path / "render.sqlite")
    accepted, _ = jobs.submit("owner-a", analysis_id, "render-atomic-key")
    render_id = UUID(accepted["render_id"])
    task_id = UUID(accepted["task_id"])
    expiry = "2099-01-01T00:00:00+00:00"
    with analysis_repository.tasks._connection() as connection:
        connection.execute(
            """INSERT INTO worker_executions (
                task_id, lease_owner, lease_expires_at, execution_token
            ) VALUES (?, ?, ?, ?)""",
            (str(task_id), "render-worker", expiry, 7),
        )
        connection.execute(
            "UPDATE tasks SET status = 'running' WHERE task_id = ?",
            (str(task_id),),
        )
    lease = WorkerLease(
        task_id=str(task_id),
        owner="render-worker",
        fencing_token=7,
        expires_at=expiry,
    )
    assert jobs.mark_running(task_id, "owner-a", lease=lease) is True

    with jobs.tasks._connection() as connection:
        reserved = connection.execute(
            "SELECT output_storage_key FROM video_render_runs WHERE render_id = ?",
            (str(render_id),),
        ).fetchone()
    assert reserved is not None
    storage_key = str(reserved["output_storage_key"])
    output_id = storage_key.removesuffix(".mp4")
    output_path = media.file_path(storage_key)
    output_path.write_bytes(b"verified-mp4-placeholder")
    record = media.register_rendered_output(
        "owner-a",
        output_id,
        storage_key,
        output_path,
        f"render-{render_id}.mp4",
        task_id=task_id,
        render_id=render_id,
        lease=lease,
        task_result={
            "render_id": str(render_id),
            "status": "completed",
            "output_asset_id": output_id,
            "duration_seconds": 3.0,
            "width": 1920,
            "height": 1080,
            "file_size": output_path.stat().st_size,
        },
    )

    assert record["asset_id"] == output_id
    assert record["media_type"] == "video/mp4"
    assert record["processing_status"] == "processed"
    assert jobs.get("owner-a", render_id)["status"] == "completed"
    assert jobs.get("owner-a", render_id)["output_asset_id"] == output_id
    assert analysis_repository.tasks.get(task_id).status.value == "succeeded"
    with analysis_repository.tasks._connection() as connection:
        execution = connection.execute(
            "SELECT result_json, finished_at FROM worker_executions WHERE task_id = ?",
            (str(task_id),),
        ).fetchone()
    assert execution["finished_at"] is not None
    assert '"output_asset_id"' in execution["result_json"]
    assert media.get("owner-b", UUID(output_id)) is None


def test_render_output_registration_rejects_stale_worker_lease(tmp_path, monkeypatch):
    _analysis_repository, analysis_id = _completed_analysis(tmp_path, monkeypatch)
    jobs = VideoRenderJobRepository(tmp_path / "render.sqlite")
    media = MediaAssetRepository(tmp_path / "render.sqlite")
    accepted, _ = jobs.submit("owner-a", analysis_id, "render-stale-key")
    render_id = UUID(accepted["render_id"])
    task_id = UUID(accepted["task_id"])
    output_id, storage_key, output_path = media.new_output_target()
    output_path.write_bytes(b"placeholder")
    stale_lease = WorkerLease(
        task_id=str(task_id),
        owner="old-worker",
        fencing_token=1,
        expires_at="2000-01-01T00:00:00+00:00",
    )

    try:
        media.register_rendered_output(
            "owner-a",
            output_id,
            storage_key,
            output_path,
            f"render-{render_id}.mp4",
            task_id=task_id,
            render_id=render_id,
            lease=stale_lease,
            task_result={"status": "completed"},
        )
    except ValueError as exc:
        assert "lease" in str(exc).lower()
    else:
        raise AssertionError("A stale worker lease must not publish an output")

    assert media.get("owner-a", UUID(output_id)) is None
    assert jobs.get("owner-a", render_id)["status"] == "accepted"


def test_render_worker_holds_fenced_media_use_leases_through_render_and_publication(
    tmp_path, monkeypatch
):
    from mrhub.video_intelligence import render_worker

    analysis_repository, analysis_id = _completed_analysis(tmp_path, monkeypatch)
    database = tmp_path / "render.sqlite"
    jobs = VideoRenderJobRepository(database)
    media = MediaAssetRepository(database)
    accepted, _ = jobs.submit("owner-a", analysis_id, "render-use-lock-key")
    task_id = UUID(accepted["task_id"])
    render_id = UUID(accepted["render_id"])
    source_id = UUID("2c83d1c5-1d8d-4c29-8a3d-4dd0e0b10a00")
    storage_key = f"{source_id}.mp4"
    source_path = media.file_path(storage_key)
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_bytes = b"source-video"
    source_path.write_bytes(source_bytes)
    now = "2026-11-04T00:00:00+00:00"

    with analysis_repository.tasks._connection() as connection:
        connection.execute(
            """INSERT INTO content_assets (
                asset_id, owner_user_id, source_asset_id, original_filename,
                media_type, storage_key, file_size, content_hash,
                processing_status, processing_profile, error_code, created_at, updated_at
            ) VALUES (?, ?, NULL, ?, 'video/mp4', ?, ?, ?, 'stored', NULL, NULL, ?, ?)""",
            (
                str(source_id), "owner-a", "source.mp4", storage_key,
                len(source_bytes), hashlib.sha256(source_bytes).hexdigest(), now, now,
            ),
        )
        connection.execute(
            """INSERT INTO worker_executions (
                task_id, attempt_count, started_at, lease_owner,
                lease_expires_at, execution_token
            ) VALUES (?, 1, ?, ?, ?, ?)""",
            (str(task_id), now, "render-worker", "2099-01-01T00:00:00+00:00", 7),
        )
        stale_time = "2000-01-01T00:00:00+00:00"
        connection.execute(
            "UPDATE tasks SET status = 'running', updated_at = ? WHERE task_id = ?",
            (stale_time, str(task_id)),
        )
        connection.execute(
            "UPDATE video_render_runs SET updated_at = ? WHERE render_id = ?",
            (stale_time, str(render_id)),
        )

    lease = WorkerLease(
        task_id=str(task_id),
        owner="render-worker",
        fencing_token=7,
        expires_at="2099-01-01T00:00:00+00:00",
    )
    observations = []

    def fake_render(**kwargs):
        with analysis_repository.tasks._connection() as connection:
            lock = connection.execute(
                "SELECT task_id, execution_token FROM media_asset_analysis_leases WHERE asset_id = ?",
                (str(source_id),),
            ).fetchone()
        observations.append(lock)
        assert lock is not None
        assert lock["task_id"] == str(task_id)
        assert lock["execution_token"] == 7
        kwargs["output_path"].write_bytes(b"rendered")
        return SimpleNamespace(
            output_path=kwargs["output_path"],
            duration_seconds=3.0,
            width=1920,
            height=1080,
            file_size=8,
        )

    monkeypatch.setattr(render_worker, "render_video_timeline", fake_render)
    task = analysis_repository.tasks.get(task_id)
    handler = VideoRenderWorkerHandler(analysis_repository.tasks)
    result = handler(task, lease=lease, lease_lost=Event())

    assert result["status"] == "completed"
    assert media.get("owner-a", UUID(result["output_asset_id"])) is not None
    assert len(observations) == 1
    with analysis_repository.tasks._connection() as connection:
        remaining = connection.execute(
            "SELECT COUNT(*) FROM media_asset_analysis_leases WHERE task_id = ?",
            (str(task_id),),
        ).fetchone()[0]
    assert remaining == 0
    assert jobs.get("owner-a", render_id)["status"] == "completed"


def test_stale_render_recovery_releases_source_lock_and_removes_reserved_orphan(
    tmp_path, monkeypatch
):
    analysis_repository, analysis_id = _completed_analysis(tmp_path, monkeypatch)
    jobs = VideoRenderJobRepository(tmp_path / "render.sqlite")
    media = MediaAssetRepository(tmp_path / "render.sqlite")
    accepted, _ = jobs.submit("owner-a", analysis_id, "render-recovery-key")
    task_id = UUID(accepted["task_id"])
    render_id = UUID(accepted["render_id"])
    source_id = UUID("2c83d1c5-1d8d-4c29-8a3d-4dd0e0b10a00")
    source_key = f"{source_id}.mp4"
    source_path = media.file_path(source_key)
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_bytes = b"source-video"
    source_path.write_bytes(source_bytes)
    now = "2026-11-04T00:00:00+00:00"

    with analysis_repository.tasks._connection() as connection:
        connection.execute(
            """INSERT INTO content_assets (
                asset_id, owner_user_id, source_asset_id, original_filename,
                media_type, storage_key, file_size, content_hash,
                processing_status, processing_profile, error_code, created_at, updated_at
            ) VALUES (?, ?, NULL, ?, 'video/mp4', ?, ?, ?, 'stored', NULL, NULL, ?, ?)""",
            (
                str(source_id), "owner-a", "source.mp4", source_key,
                len(source_bytes), hashlib.sha256(source_bytes).hexdigest(), now, now,
            ),
        )
        connection.execute(
            "UPDATE tasks SET status = 'running', updated_at = ? WHERE task_id = ?",
            (now, str(task_id)),
        )
        connection.execute(
            "UPDATE video_render_runs SET status = 'running' WHERE render_id = ?",
            (str(render_id),),
        )
        connection.execute(
            "UPDATE idempotency_records SET status = 'running' WHERE task_id = ?",
            (str(task_id),),
        )
        connection.execute(
            """INSERT INTO worker_executions (
                task_id, attempt_count, started_at, lease_owner,
                lease_expires_at, execution_token
            ) VALUES (?, 1, ?, ?, ?, ?)""",
            (
                str(task_id), "2000-01-01T00:00:00+00:00",
                "dead-worker", "2000-01-01T00:00:00+00:00", 7,
            ),
        )
        connection.execute(
            """INSERT INTO media_asset_analysis_leases (
                lease_id, asset_id, owner_user_id, task_id,
                lease_owner, execution_token, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                "lease-orphan", str(source_id), "owner-a", str(task_id),
                "dead-worker", 7, now,
            ),
        )
        reserved = connection.execute(
            "SELECT output_storage_key FROM video_render_runs WHERE render_id = ?",
            (str(render_id),),
        ).fetchone()["output_storage_key"]

    orphan_path = media.file_path(reserved)
    orphan_path.write_bytes(b"orphaned-render-output")
    worker = WorkerEngine(
        analysis_repository.tasks,
        clock=lambda: datetime(2026, 11, 4, tzinfo=UTC),
    )

    worker._recover_interrupted()
    assert analysis_repository.tasks.get(task_id).status.value == "failed"
    assert jobs.get("owner-a", render_id)["status"] == "failed"
    assert orphan_path.exists() is False
    with analysis_repository.tasks._connection() as connection:
        remaining_locks = connection.execute(
            "SELECT COUNT(*) FROM media_asset_analysis_leases WHERE task_id = ?",
            (str(task_id),),
        ).fetchone()[0]
        idempotency = connection.execute(
            "SELECT status FROM idempotency_records WHERE task_id = ?",
            (str(task_id),),
        ).fetchone()["status"]
    assert remaining_locks == 0
    assert idempotency == "failed"


def test_render_output_registration_rejects_unreserved_storage_key(tmp_path, monkeypatch):
    analysis_repository, analysis_id = _completed_analysis(tmp_path, monkeypatch)
    jobs = VideoRenderJobRepository(tmp_path / "render.sqlite")
    media = MediaAssetRepository(tmp_path / "render.sqlite")
    accepted, _ = jobs.submit("owner-a", analysis_id, "render-reserved-key")
    render_id = UUID(accepted["render_id"])
    task_id = UUID(accepted["task_id"])
    now = "2026-11-04T00:00:00+00:00"
    with analysis_repository.tasks._connection() as connection:
        connection.execute(
            """INSERT INTO worker_executions (
                task_id, attempt_count, started_at, lease_owner,
                lease_expires_at, execution_token
            ) VALUES (?, 1, ?, ?, ?, ?)""",
            (
                str(task_id), now, "render-worker",
                "2099-01-01T00:00:00+00:00", 9,
            ),
        )
        connection.execute(
            "UPDATE tasks SET status = 'running', updated_at = ? WHERE task_id = ?",
            (now, str(task_id)),
        )
    lease = WorkerLease(
        task_id=str(task_id),
        owner="render-worker",
        fencing_token=9,
        expires_at="2099-01-01T00:00:00+00:00",
    )
    assert jobs.mark_running(task_id, "owner-a", lease=lease) is True

    output_id, storage_key, output_path = media.new_output_target()
    output_path.write_bytes(b"unreserved-output")
    try:
        media.register_rendered_output(
            "owner-a",
            output_id,
            storage_key,
            output_path,
            f"render-{render_id}.mp4",
            task_id=task_id,
            render_id=render_id,
            lease=lease,
            task_result={"status": "completed"},
        )
    except ValueError as exc:
        assert "no longer owned" in str(exc)
    else:
        raise AssertionError("A render cannot publish to a key it did not reserve")

    assert media.get("owner-a", UUID(output_id)) is None
    assert jobs.get("owner-a", render_id)["status"] == "running"


def test_render_cancellation_is_owner_scoped_and_terminal_when_queued(
    tmp_path, monkeypatch
):
    analysis_repository, analysis_id = _completed_analysis(tmp_path, monkeypatch)
    jobs = VideoRenderJobRepository(tmp_path / "render.sqlite")
    accepted, _ = jobs.submit("owner-a", analysis_id, "render-cancel-queued")
    render_id = UUID(accepted["render_id"])
    task_id = UUID(accepted["task_id"])

    assert jobs.cancel("owner-b", render_id) is None
    cancelled = jobs.cancel("owner-a", render_id)
    assert cancelled == {
        "render_id": str(render_id),
        "status": "cancelled",
        "cancellation_requested": False,
    }
    assert jobs.get("owner-a", render_id)["status"] == "cancelled"
    assert analysis_repository.tasks.get(task_id).status.value == "cancelled"
    with analysis_repository.tasks._connection() as connection:
        status = connection.execute(
            "SELECT status FROM idempotency_records WHERE task_id = ?",
            (str(task_id),),
        ).fetchone()["status"]
    assert status == "failed"


def test_running_render_cancellation_signals_worker_without_publishing(
    tmp_path, monkeypatch
):
    analysis_repository, analysis_id = _completed_analysis(tmp_path, monkeypatch)
    jobs = VideoRenderJobRepository(tmp_path / "render.sqlite")
    accepted, _ = jobs.submit("owner-a", analysis_id, "render-cancel-running")
    render_id = UUID(accepted["render_id"])
    task_id = UUID(accepted["task_id"])
    expiry = "2099-01-01T00:00:00+00:00"
    with analysis_repository.tasks._connection() as connection:
        connection.execute(
            """INSERT INTO worker_executions (
                task_id, attempt_count, started_at, lease_owner,
                lease_expires_at, execution_token
            ) VALUES (?, 1, ?, ?, ?, ?)""",
            (
                str(task_id), "2026-11-04T00:00:00+00:00",
                "render-worker", expiry, 11,
            ),
        )
        connection.execute(
            "UPDATE tasks SET status = 'running' WHERE task_id = ?",
            (str(task_id),),
        )
    lease = WorkerLease(
        task_id=str(task_id),
        owner="render-worker",
        fencing_token=11,
        expires_at=expiry,
    )
    assert jobs.mark_running(task_id, "owner-a", lease=lease) is True

    cancelled = jobs.cancel("owner-a", render_id)
    assert cancelled == {
        "render_id": str(render_id),
        "status": "running",
        "cancellation_requested": True,
    }
    assert analysis_repository.tasks.get(task_id).status.value == "cancelled"
    # The worker owns the terminal render transition after it observes cancellation.
    assert jobs.get("owner-a", render_id)["status"] == "running"


def test_render_worker_observes_preexisting_cancellation_before_media_access(
    tmp_path, monkeypatch
):
    analysis_repository, analysis_id = _completed_analysis(tmp_path, monkeypatch)
    jobs = VideoRenderJobRepository(tmp_path / "render.sqlite")
    media = MediaAssetRepository(tmp_path / "render.sqlite")
    accepted, _ = jobs.submit("owner-a", analysis_id, "render-cancel-before-worker")
    render_id = UUID(accepted["render_id"])
    task_id = UUID(accepted["task_id"])
    expiry = "2099-01-01T00:00:00+00:00"
    with analysis_repository.tasks._connection() as connection:
        connection.execute(
            """INSERT INTO worker_executions (
                task_id, attempt_count, started_at, lease_owner,
                lease_expires_at, execution_token
            ) VALUES (?, 1, ?, ?, ?, ?)""",
            (
                str(task_id), "2026-11-04T00:00:00+00:00",
                "render-worker", expiry, 13,
            ),
        )
        connection.execute(
            "UPDATE tasks SET status = 'cancelled' WHERE task_id = ?",
            (str(task_id),),
        )
        reserved = connection.execute(
            "SELECT output_storage_key FROM video_render_runs WHERE render_id = ?",
            (str(render_id),),
        ).fetchone()["output_storage_key"]
    lease = WorkerLease(
        task_id=str(task_id),
        owner="render-worker",
        fencing_token=13,
        expires_at=expiry,
    )

    result = VideoRenderWorkerHandler(analysis_repository.tasks)(
        analysis_repository.tasks.get(task_id),
        lease=lease,
        lease_lost=Event(),
    )

    assert result == {"render_id": str(render_id), "status": "cancelled"}
    assert jobs.get("owner-a", render_id)["status"] == "cancelled"
    assert media.file_path(reserved).exists() is False
    with analysis_repository.tasks._connection() as connection:
        locks = connection.execute(
            "SELECT COUNT(*) FROM media_asset_analysis_leases WHERE task_id = ?",
            (str(task_id),),
        ).fetchone()[0]
    assert locks == 0
