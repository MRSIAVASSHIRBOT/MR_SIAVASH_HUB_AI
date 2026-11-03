import base64
from uuid import UUID

from mrhub.jobs.leases import WorkerLease
from mrhub.media.repository import MediaAssetRepository
from mrhub.video_intelligence.jobs import VideoAnalysisJobRepository
from mrhub.video_intelligence.render_jobs import (
    VideoRenderJobRepository,
)
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

    output_id, storage_key, output_path = media.new_output_target()
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
    analysis_repository, analysis_id = _completed_analysis(tmp_path, monkeypatch)
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
