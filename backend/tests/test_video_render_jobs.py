import base64
import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from threading import Event
from types import SimpleNamespace
from uuid import UUID

import pytest

from mrhub.jobs.leases import WorkerLease
from mrhub.jobs.worker import WorkerEngine
from mrhub.media.repository import MediaAssetRepository
from mrhub.video_intelligence.jobs import VideoAnalysisJobRepository
from mrhub.video_intelligence.render_jobs import VideoRenderConflict, VideoRenderJobRepository
from mrhub.video_intelligence.render_snapshot import VideoRenderTimelineSnapshot
from mrhub.video_intelligence.render_snapshot_repository import (
    VideoRenderSnapshotConflict,
    VideoRenderSnapshotRepository,
)
from mrhub.video_intelligence.render_worker import VideoRenderWorkerHandler
from mrhub.video_intelligence.schemas import AnalysisMode, VideoAnalysisRequest
from mrhub.video_intelligence.timeline import VideoTimeline
from mrhub.video_intelligence.timeline_drafts import (
    TimelineDraftUpdate,
    VideoTimelineDraftRepository,
)


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
            "assets": [{
                "asset_id": source_id,
                "technical_metadata": {"duration_seconds": 3.0},
            }],
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
    output_asset_id = reserved.removesuffix(".mp4")
    partial_path = media.storage_root / f".{output_asset_id}.{'a' * 32}.partial.mp4"
    partial_path.write_bytes(b"interrupted-ffmpeg-output")
    unrelated_partial = media.storage_root / f".{UUID('4c83d1c5-1d8d-4c29-8a3d-4dd0e0b10a00')}.{'b' * 32}.partial.mp4"
    unrelated_partial.write_bytes(b"belongs-to-another-render")
    worker = WorkerEngine(
        analysis_repository.tasks,
        clock=lambda: datetime(2026, 11, 4, tzinfo=UTC),
    )

    worker._recover_interrupted()
    assert analysis_repository.tasks.get(task_id).status.value == "failed"
    assert jobs.get("owner-a", render_id)["status"] == "failed"
    assert orphan_path.exists() is False
    assert partial_path.exists() is False
    assert unrelated_partial.exists() is True
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



def test_render_snapshot_repository_persists_owner_scoped_immutable_revision(
    tmp_path, monkeypatch
):
    analysis_repository, analysis_id = _completed_analysis(tmp_path, monkeypatch)
    database = tmp_path / "render.sqlite"
    draft_repository = VideoTimelineDraftRepository(database)
    source_id = UUID("2c83d1c5-1d8d-4c29-8a3d-4dd0e0b10a00")
    draft = draft_repository.create(
        "owner-a",
        analysis_id,
        source_id,
        3,
        "16:9",
        [{"start_seconds": 0, "end_seconds": 3, "generation_instruction": "Use the source interval"}],
    )
    analysis = analysis_repository.get("owner-a", analysis_id)
    assert analysis is not None
    timeline = VideoTimeline.model_validate(analysis["result"]["timeline"])
    draft = draft_repository.update(
        "owner-a",
        UUID(draft["draft_id"]),
        TimelineDraftUpdate(
            expected_version=1,
            duration_seconds=3,
            aspect_ratio="16:9",
            beats=[{"start_seconds": 0, "end_seconds": 3, "generation_instruction": "Use the source interval"}],
            renderer_timeline=timeline,
        ),
    )
    assert draft is not None
    assert draft["renderer_timeline_sha256"]
    snapshot = VideoRenderTimelineSnapshot.create(
        owner_user_id="owner-a",
        analysis_id=analysis_id,
        draft_id=UUID(draft["draft_id"]),
        draft_version=2,
        timeline=timeline,
        analysis_source_asset_ids=[str(source_id)],
    )
    repository = VideoRenderSnapshotRepository(database)

    stored, created = repository.create(snapshot)
    assert created is True
    assert stored.snapshot_id == snapshot.snapshot_id
    assert stored.timeline_sha256 == snapshot.timeline_sha256
    assert repository.get("owner-a", snapshot.snapshot_id).timeline_json == snapshot.timeline_json
    assert repository.get("owner-b", snapshot.snapshot_id) is None

    replay, replay_created = repository.create(snapshot)
    assert replay_created is False
    assert replay.snapshot_id == stored.snapshot_id

    render_jobs = VideoRenderJobRepository(database)
    accepted_render, render_created = render_jobs.submit(
        "owner-a",
        analysis_id,
        "snapshot-persistence-render-key",
        snapshot_id=stored.snapshot_id,
    )
    assert render_created is True
    loaded_render = render_jobs.load_for_worker(UUID(accepted_render["task_id"]))
    assert loaded_render is not None
    assert loaded_render[4] == stored.snapshot_id
    replay_render, replay_render_created = render_jobs.submit(
        "owner-a",
        analysis_id,
        "snapshot-persistence-render-key",
        snapshot_id=stored.snapshot_id,
    )
    assert replay_render_created is False
    assert replay_render["render_id"] == accepted_render["render_id"]

    with repository.tasks._connection() as connection, pytest.raises(
        sqlite3.IntegrityError, match="immutable"
    ):
        connection.execute(
            "UPDATE video_render_timeline_snapshots SET timeline_sha256 = ? WHERE snapshot_id = ?",
            ("0" * 64, str(snapshot.snapshot_id)),
        )

    with repository.tasks._connection() as connection, pytest.raises(
        sqlite3.IntegrityError, match="FOREIGN KEY"
    ):
        connection.execute(
            "DELETE FROM video_timeline_drafts WHERE draft_id = ?",
            (str(draft["draft_id"]),),
        )

    with repository.tasks._connection() as connection, pytest.raises(
        sqlite3.IntegrityError, match="renderer timeline and hash must be stored together"
    ):
        connection.execute(
            """UPDATE video_timeline_drafts
               SET renderer_timeline_sha256 = NULL WHERE draft_id = ?""",
            (str(draft["draft_id"]),),
        )

    with repository.tasks._connection() as connection, pytest.raises(
        sqlite3.IntegrityError, match="renderer timeline and hash must be stored together"
    ):
        connection.execute(
            """INSERT INTO video_timeline_drafts (
                draft_id, owner_user_id, analysis_id, asset_id, duration_seconds,
                aspect_ratio, timeline_json, version, created_at, updated_at,
                renderer_timeline_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?)""",
            (
                "7f3e5e1a-ff47-4e2c-8c0d-6e1a3a2f6a11",
                "owner-a",
                str(analysis_id),
                str(source_id),
                3,
                "16:9",
                "[]",
                "2026-11-04T00:00:00+00:00",
                "2026-11-04T00:00:00+00:00",
                "{}",
            ),
        )

    advanced = draft_repository.update(
        "owner-a",
        UUID(draft["draft_id"]),
        TimelineDraftUpdate(
            expected_version=2,
            duration_seconds=3,
            aspect_ratio="16:9",
            beats=[{"start_seconds": 0, "end_seconds": 3, "generation_instruction": "A newer draft revision"}],
        ),
    )
    assert advanced is not None and advanced["version"] == 3
    replay_after_advance, replay_after_advance_created = repository.create(snapshot)
    assert replay_after_advance_created is False
    assert replay_after_advance.snapshot_id == stored.snapshot_id

    # A retry of the already accepted operation remains idempotent even after
    # the editable draft advances; this is not a new render submission.
    replay_accepted_after_advance, replay_accepted_created = render_jobs.submit(
        "owner-a",
        analysis_id,
        "snapshot-persistence-render-key",
        snapshot_id=stored.snapshot_id,
    )
    assert replay_accepted_created is False
    assert replay_accepted_after_advance["render_id"] == accepted_render["render_id"]

    # Historical snapshot replay is read-only; a new render must use the
    # currently persisted draft revision, not the stale revision's snapshot.
    with pytest.raises(
        VideoRenderSnapshotConflict, match="current owner-scoped draft revision"
    ):
        render_jobs.submit(
            "owner-a",
            analysis_id,
            "stale-snapshot-new-render-key",
            snapshot=snapshot,
        )
    with pytest.raises(
        VideoRenderSnapshotConflict, match="current owner-scoped draft revision"
    ):
        render_jobs.submit(
            "owner-a",
            analysis_id,
            "stale-snapshot-id-new-render-key",
            snapshot_id=stored.snapshot_id,
        )
    with repository.tasks._connection() as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM video_render_runs"
        ).fetchone()[0] == 1


def test_render_snapshot_repository_rejects_stale_draft_revision(
    tmp_path, monkeypatch
):
    analysis_repository, analysis_id = _completed_analysis(tmp_path, monkeypatch)
    database = tmp_path / "render.sqlite"
    source_id = UUID("2c83d1c5-1d8d-4c29-8a3d-4dd0e0b10a00")
    draft_repository = VideoTimelineDraftRepository(database)
    draft = draft_repository.create(
        "owner-a",
        analysis_id,
        source_id,
        3,
        "16:9",
        [{"start_seconds": 0, "end_seconds": 3, "generation_instruction": "Original draft"}],
    )
    analysis = analysis_repository.get("owner-a", analysis_id)
    timeline = VideoTimeline.model_validate(analysis["result"]["timeline"])
    draft = draft_repository.update(
        "owner-a",
        UUID(draft["draft_id"]),
        TimelineDraftUpdate(
            expected_version=1,
            duration_seconds=3,
            aspect_ratio="16:9",
            beats=[{"start_seconds": 0, "end_seconds": 3, "generation_instruction": "Original draft"}],
            renderer_timeline=timeline,
        ),
    )
    snapshot = VideoRenderTimelineSnapshot.create(
        owner_user_id="owner-a",
        analysis_id=analysis_id,
        draft_id=UUID(draft["draft_id"]),
        draft_version=2,
        timeline=timeline,
        analysis_source_asset_ids=[str(source_id)],
    )
    updated_draft = draft_repository.update(
        "owner-a",
        UUID(draft["draft_id"]),
        TimelineDraftUpdate(
            expected_version=2,
            duration_seconds=3,
            aspect_ratio="16:9",
            beats=[{"start_seconds": 0, "end_seconds": 3, "generation_instruction": "Updated draft"}],
        ),
    )
    assert updated_draft is not None
    assert updated_draft["renderer_timeline"] is None
    assert updated_draft["renderer_timeline_sha256"] is None

    with pytest.raises(VideoRenderSnapshotConflict, match="current owner-scoped draft revision"):
        VideoRenderSnapshotRepository(database).create(snapshot)



def test_renderer_timeline_rejects_source_interval_past_actual_media_duration(
    tmp_path, monkeypatch
):
    analysis_repository, analysis_id = _completed_analysis(tmp_path, monkeypatch)
    database = tmp_path / "render.sqlite"
    draft_repository = VideoTimelineDraftRepository(database)
    source_id = UUID("2c83d1c5-1d8d-4c29-8a3d-4dd0e0b10a00")
    draft = draft_repository.create(
        "owner-a",
        analysis_id,
        source_id,
        3,
        "16:9",
        [{"start_seconds": 0, "end_seconds": 3, "generation_instruction": "Use source"}],
    )
    analysis = analysis_repository.get("owner-a", analysis_id)
    assert analysis is not None
    timeline_data = dict(analysis["result"]["timeline"])
    clip = dict(timeline_data["video_track"][0])
    clip["source_start_seconds"] = 0.1
    clip["source_end_seconds"] = 3.1
    timeline_data["video_track"] = [clip]
    invalid_timeline = VideoTimeline.model_validate(timeline_data)

    with pytest.raises(ValueError, match="source interval exceeds source duration"):
        draft_repository.update(
            "owner-a",
            UUID(draft["draft_id"]),
            TimelineDraftUpdate(
                expected_version=1,
                duration_seconds=3,
                aspect_ratio="16:9",
                beats=[{"start_seconds": 0, "end_seconds": 3, "generation_instruction": "Use source"}],
                renderer_timeline=invalid_timeline,
            ),
        )


def test_snapshot_repository_revalidates_source_duration_before_persisting(
    tmp_path, monkeypatch
):
    analysis_repository, analysis_id = _completed_analysis(tmp_path, monkeypatch)
    database = tmp_path / "render.sqlite"
    draft_repository = VideoTimelineDraftRepository(database)
    source_id = UUID("2c83d1c5-1d8d-4c29-8a3d-4dd0e0b10a00")
    draft = draft_repository.create(
        "owner-a",
        analysis_id,
        source_id,
        3,
        "16:9",
        [{"start_seconds": 0, "end_seconds": 3, "generation_instruction": "Use source"}],
    )
    analysis = analysis_repository.get("owner-a", analysis_id)
    assert analysis is not None
    valid_timeline = VideoTimeline.model_validate(analysis["result"]["timeline"])
    saved = draft_repository.update(
        "owner-a",
        UUID(draft["draft_id"]),
        TimelineDraftUpdate(
            expected_version=1,
            duration_seconds=3,
            aspect_ratio="16:9",
            beats=[{"start_seconds": 0, "end_seconds": 3, "generation_instruction": "Use source"}],
            renderer_timeline=valid_timeline,
        ),
    )
    assert saved is not None

    invalid_data = dict(analysis["result"]["timeline"])
    clip = dict(invalid_data["video_track"][0])
    clip["source_start_seconds"] = 0.1
    clip["source_end_seconds"] = 3.1
    invalid_data["video_track"] = [clip]
    invalid_timeline = VideoTimeline.model_validate(invalid_data)
    canonical = json.dumps(
        invalid_timeline.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    with draft_repository.tasks._connection() as connection:
        connection.execute(
            """UPDATE video_timeline_drafts
               SET renderer_timeline_json = ?, renderer_timeline_sha256 = ?
               WHERE draft_id = ? AND version = 2""",
            (canonical, digest, draft["draft_id"]),
        )

    snapshot = VideoRenderTimelineSnapshot.create(
        owner_user_id="owner-a",
        analysis_id=analysis_id,
        draft_id=UUID(draft["draft_id"]),
        draft_version=2,
        timeline=invalid_timeline,
        analysis_source_asset_ids=[str(source_id)],
    )
    with pytest.raises(ValueError, match="source interval exceeds source duration"):
        VideoRenderSnapshotRepository(database).create(snapshot)



def test_snapshot_backed_worker_renders_frozen_draft_timeline(
    tmp_path, monkeypatch
):
    import mrhub.video_intelligence.render_worker as render_worker_module

    analysis_repository, analysis_id = _completed_analysis(tmp_path, monkeypatch)
    database = tmp_path / "render.sqlite"
    drafts = VideoTimelineDraftRepository(database)
    source_id = UUID("2c83d1c5-1d8d-4c29-8a3d-4dd0e0b10a00")
    draft = drafts.create(
        "owner-a",
        analysis_id,
        source_id,
        3,
        "16:9",
        [{"start_seconds": 0, "end_seconds": 3, "generation_instruction": "Use edited source interval"}],
    )

    analysis = analysis_repository.get("owner-a", analysis_id)
    assert analysis is not None
    timeline_data = dict(analysis["result"]["timeline"])
    clip = dict(timeline_data["video_track"][0])
    clip["source_start_seconds"] = 1.0
    clip["source_end_seconds"] = 3.0
    clip["timeline_start_seconds"] = 0.0
    clip["timeline_end_seconds"] = 2.0
    timeline_data["video_track"] = [clip]
    timeline_data["actual_duration_seconds"] = 2.0
    timeline_data["duration_shortfall_seconds"] = 1.0
    edited_timeline = VideoTimeline.model_validate(timeline_data)

    saved = drafts.update(
        "owner-a",
        UUID(draft["draft_id"]),
        TimelineDraftUpdate(
            expected_version=1,
            duration_seconds=3,
            aspect_ratio="16:9",
            beats=[{"start_seconds": 0, "end_seconds": 3, "generation_instruction": "Use edited source interval"}],
            renderer_timeline=edited_timeline,
        ),
    )
    assert saved is not None
    snapshot = VideoRenderTimelineSnapshot.create(
        owner_user_id="owner-a",
        analysis_id=analysis_id,
        draft_id=UUID(draft["draft_id"]),
        draft_version=saved["version"],
        timeline=edited_timeline,
        analysis_source_asset_ids=[str(source_id)],
    )

    jobs = VideoRenderJobRepository(database)
    accepted, created = jobs.submit(
        "owner-a",
        analysis_id,
        "snapshot-render-key",
        snapshot=snapshot,
    )
    assert created is True
    assert accepted["snapshot_id"] == str(snapshot.snapshot_id)
    persisted = VideoRenderSnapshotRepository(database).get(
        "owner-a", UUID(accepted["snapshot_id"])
    )
    assert persisted is not None
    assert persisted.timeline_sha256 == snapshot.timeline_sha256
    task_id = UUID(accepted["task_id"])
    render_id = UUID(accepted["render_id"])
    media = MediaAssetRepository(database)
    source_key = f"{source_id}.mp4"
    source_path = media.file_path(source_key)
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_bytes = b"source-video"
    source_path.write_bytes(source_bytes)
    now = "2026-11-04T00:00:00+00:00"
    expiry = "2099-01-01T00:00:00+00:00"
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
            """INSERT INTO worker_executions (
                task_id, attempt_count, started_at, lease_owner,
                lease_expires_at, execution_token
            ) VALUES (?, 1, ?, ?, ?, ?)""",
            (str(task_id), now, "snapshot-render-worker", expiry, 19),
        )
        connection.execute(
            "UPDATE tasks SET status = 'running', updated_at = ? WHERE task_id = ?",
            (now, str(task_id)),
        )

    lease = WorkerLease(
        task_id=str(task_id),
        owner="snapshot-render-worker",
        fencing_token=19,
        expires_at=expiry,
    )
    observed = {}

    def fake_render(**kwargs):
        observed["timeline"] = kwargs["timeline"]
        kwargs["output_path"].write_bytes(b"snapshot-rendered")
        return SimpleNamespace(
            output_path=kwargs["output_path"],
            duration_seconds=2.0,
            width=1920,
            height=1080,
            file_size=18,
        )

    monkeypatch.setattr(render_worker_module, "render_video_timeline", fake_render)
    task = analysis_repository.tasks.get(task_id)
    result = VideoRenderWorkerHandler(analysis_repository.tasks)(
        task, lease=lease, lease_lost=Event()
    )

    assert result["status"] == "completed"
    assert observed["timeline"].video_track[0].source_start_seconds == 1.0
    assert jobs.get("owner-a", render_id)["status"] == "completed"
    assert media.get("owner-a", UUID(result["output_asset_id"])) is not None

def test_snapshot_and_render_submission_roll_back_together_on_idempotency_conflict(
    tmp_path, monkeypatch
):
    analysis_repository, analysis_id = _completed_analysis(tmp_path, monkeypatch)
    database = tmp_path / "render.sqlite"
    jobs = VideoRenderJobRepository(database)
    jobs.submit("owner-a", analysis_id, "shared-idempotency-key")

    source_id = UUID("2c83d1c5-1d8d-4c29-8a3d-4dd0e0b10a00")
    drafts = VideoTimelineDraftRepository(database)
    draft = drafts.create(
        "owner-a",
        analysis_id,
        source_id,
        3,
        "16:9",
        [{"start_seconds": 0, "end_seconds": 3, "generation_instruction": "Use source"}],
    )
    analysis = analysis_repository.get("owner-a", analysis_id)
    assert analysis is not None
    timeline = VideoTimeline.model_validate(analysis["result"]["timeline"])
    saved = drafts.update(
        "owner-a",
        UUID(draft["draft_id"]),
        TimelineDraftUpdate(
            expected_version=1,
            duration_seconds=3,
            aspect_ratio="16:9",
            beats=[{"start_seconds": 0, "end_seconds": 3, "generation_instruction": "Use source"}],
            renderer_timeline=timeline,
        ),
    )
    assert saved is not None
    snapshot = VideoRenderTimelineSnapshot.create(
        owner_user_id="owner-a",
        analysis_id=analysis_id,
        draft_id=UUID(draft["draft_id"]),
        draft_version=saved["version"],
        timeline=timeline,
        analysis_source_asset_ids=[str(source_id)],
    )

    with pytest.raises(VideoRenderConflict, match="Idempotency key conflicts"):
        jobs.submit(
            "owner-a",
            analysis_id,
            "shared-idempotency-key",
            snapshot=snapshot,
        )

    assert VideoRenderSnapshotRepository(database).get(
        "owner-a", snapshot.snapshot_id
    ) is None
    with jobs.tasks._connection() as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM video_render_timeline_snapshots"
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM video_render_runs"
        ).fetchone()[0] == 1




def test_snapshot_and_render_submission_share_one_transaction(tmp_path, monkeypatch):
    analysis_repository, analysis_id = _completed_analysis(tmp_path, monkeypatch)
    database = tmp_path / "render.sqlite"
    drafts = VideoTimelineDraftRepository(database)
    source_id = UUID("2c83d1c5-1d8d-4c29-8a3d-4dd0e0b10a00")
    draft = drafts.create(
        "owner-a",
        analysis_id,
        source_id,
        3,
        "16:9",
        [{"start_seconds": 0, "end_seconds": 3, "generation_instruction": "Atomic render"}],
    )
    analysis = analysis_repository.get("owner-a", analysis_id)
    assert analysis is not None
    timeline = VideoTimeline.model_validate(analysis["result"]["timeline"])
    saved = drafts.update(
        "owner-a",
        UUID(draft["draft_id"]),
        TimelineDraftUpdate(
            expected_version=1,
            duration_seconds=3,
            aspect_ratio="16:9",
            beats=[{"start_seconds": 0, "end_seconds": 3, "generation_instruction": "Atomic render"}],
            renderer_timeline=timeline,
        ),
    )
    assert saved is not None
    snapshot = VideoRenderTimelineSnapshot.create(
        owner_user_id="owner-a",
        analysis_id=analysis_id,
        draft_id=UUID(draft["draft_id"]),
        draft_version=saved["version"],
        timeline=timeline,
        analysis_source_asset_ids=[str(source_id)],
    )
    jobs = VideoRenderJobRepository(database)

    legacy, _ = jobs.submit("owner-a", analysis_id, "atomic-snapshot-key")
    with pytest.raises(VideoRenderConflict):
        jobs.submit(
            "owner-a",
            analysis_id,
            "atomic-snapshot-key",
            snapshot=snapshot,
        )

    with jobs.tasks._connection() as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM video_render_timeline_snapshots"
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM video_render_runs"
        ).fetchone()[0] == 1

    accepted, created = jobs.submit(
        "owner-a",
        analysis_id,
        "atomic-snapshot-key-2",
        snapshot=snapshot,
    )
    assert created is True
    snapshot_id = UUID(accepted["snapshot_id"])
    stored = VideoRenderSnapshotRepository(database).get("owner-a", snapshot_id)
    assert stored is not None
    assert stored.timeline_sha256 == snapshot.timeline_sha256
    with jobs.tasks._connection() as connection:
        linked = connection.execute(
            "SELECT snapshot_id FROM video_render_runs WHERE render_id = ?",
            (accepted["render_id"],),
        ).fetchone()
        assert linked is not None and linked["snapshot_id"] == str(snapshot_id)
        assert connection.execute(
            "SELECT COUNT(*) FROM video_render_runs"
        ).fetchone()[0] == 2
    assert legacy["render_id"] != accepted["render_id"]
