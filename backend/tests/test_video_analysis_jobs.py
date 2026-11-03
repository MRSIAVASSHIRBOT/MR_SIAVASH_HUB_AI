import base64
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from mrhub.domain.tasks import TaskStatus

from mrhub.jobs.leases import WorkerLease
from mrhub.jobs.payload_envelope import PayloadEnvelopeError
from mrhub.jobs.worker import WorkerEngine
from mrhub.media.repository import MediaAssetBusy, MediaAssetRepository
from mrhub.video_intelligence.jobs import (
    VideoAnalysisConflict,
    VideoAnalysisJobRepository,
)
from mrhub.video_intelligence.schemas import AnalysisMode, VideoAnalysisRequest


def _repository(tmp_path):
    repository = VideoAnalysisJobRepository(tmp_path / "analysis.sqlite")
    repository.tasks.create_auth_user("owner-a", "owner-a", "salt-a", "hash-a")
    repository.tasks.create_auth_user("owner-b", "owner-b", "salt-b", "hash-b")
    return repository


def _request(asset_id: str) -> VideoAnalysisRequest:
    return VideoAnalysisRequest(
        mode=AnalysisMode.FAITHFUL,
        source_asset_ids=[asset_id],
        duration_seconds=20,
    )


def test_submit_is_atomic_idempotent_and_owner_scoped(tmp_path, monkeypatch):
    monkeypatch.setenv(
        "MRH_WORKFLOW_PAYLOAD_KEY",
        base64.urlsafe_b64encode(b"k" * 32).decode("ascii"),
    )
    repository = _repository(tmp_path)
    asset_id = "2c83d1c5-1d8d-4c29-8a3d-4dd0e0b10a00"

    accepted, created = repository.submit("owner-a", _request(asset_id), "request-1")
    assert created is True
    assert accepted["status"] == "accepted"

    replay, replay_created = repository.submit("owner-a", _request(asset_id), "request-1")
    assert replay_created is False
    assert replay["analysis_id"] == accepted["analysis_id"]
    assert replay["task_id"] == accepted["task_id"]

    assert repository.get("owner-b", UUID(accepted["analysis_id"])) is None
    assert repository.get("owner-a", UUID(accepted["analysis_id"]))["status"] == "accepted"

    with pytest.raises(VideoAnalysisConflict):
        repository.submit(
            "owner-a",
            VideoAnalysisRequest(
                mode=AnalysisMode.FUSION,
                source_asset_ids=[asset_id],
                duration_seconds=20,
            ),
            "request-1",
        )


def test_analysis_payload_is_encrypted_and_removed_after_terminal_result(
    tmp_path, monkeypatch
):
    monkeypatch.setenv(
        "MRH_WORKFLOW_PAYLOAD_KEY",
        base64.urlsafe_b64encode(b"z" * 32).decode("ascii"),
    )
    repository = _repository(tmp_path)
    accepted, _ = repository.submit(
        "owner-a",
        _request("2c83d1c5-1d8d-4c29-8a3d-4dd0e0b10a00"),
        "request-2",
    )
    task_id = UUID(accepted["task_id"])
    loaded = repository.load_for_worker(task_id)
    assert loaded is not None
    owner, analysis_id, payload = loaded
    assert owner == "owner-a"
    assert str(analysis_id) == accepted["analysis_id"]
    assert payload["source_asset_ids"] == ["2c83d1c5-1d8d-4c29-8a3d-4dd0e0b10a00"]

    lease_expiry = "2099-01-01T00:00:00+00:00"
    with repository.tasks._connection() as connection:
        connection.execute(
            """INSERT INTO worker_executions (
                task_id, lease_owner, lease_expires_at, execution_token
            ) VALUES (?, ?, ?, ?)""",
            (str(task_id), "worker-a", lease_expiry, 1),
        )
    lease = WorkerLease(
        task_id=str(task_id), owner="worker-a",
        fencing_token=1, expires_at=lease_expiry,
    )
    repository.finish(
        task_id, owner, status="completed",
        result={"semantic_visual_analysis": False}, lease=lease,
    )
    record = repository.get(owner, analysis_id)
    assert record["status"] == "completed"
    assert record["result"]["semantic_visual_analysis"] is False
    assert repository.load_for_worker(task_id) is None


def test_submit_fails_closed_without_encryption_key(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from mrhub.jobs import payload_envelope

    monkeypatch.delenv("MRH_WORKFLOW_PAYLOAD_KEY", raising=False)
    monkeypatch.setattr(
        payload_envelope,
        "get_settings",
        lambda: SimpleNamespace(workflow_payload_key=None),
    )
    repository = _repository(tmp_path)
    with pytest.raises(PayloadEnvelopeError):
        repository.submit(
            "owner-a",
            _request("2c83d1c5-1d8d-4c29-8a3d-4dd0e0b10a00"),
            "request-3",
        )



def test_stale_worker_recovery_releases_orphaned_asset_use_locks(
    tmp_path, monkeypatch
):
    monkeypatch.setenv(
        "MRH_WORKFLOW_PAYLOAD_KEY",
        base64.urlsafe_b64encode(b"r" * 32).decode("ascii"),
    )
    repository = _repository(tmp_path)
    media = MediaAssetRepository(repository.database_path)
    asset = media.store_upload(
        "owner-a", "recovery.mp4", "video/mp4", b"recovery-video-fixture"
    )
    asset_id = UUID(str(asset["asset_id"]))
    accepted, created = repository.submit(
        "owner-a", _request(str(asset_id)), "recovery-idempotency-key"
    )
    assert created is True
    task_id = UUID(accepted["task_id"])

    now = datetime.now(UTC)
    started_at = (now - timedelta(minutes=10)).isoformat()
    expired_at = (now - timedelta(minutes=5)).isoformat()
    with repository.tasks._connection() as connection:
        connection.execute(
            "UPDATE tasks SET status = 'running' WHERE task_id = ?",
            (str(task_id),),
        )
        connection.execute(
            "UPDATE video_analysis_runs SET status = 'running' WHERE task_id = ?",
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
            (
                "stale-analysis-lock",
                str(asset_id),
                "owner-a",
                str(task_id),
                started_at,
            ),
        )

    # Lease expiry alone does not unblock deletion; stale recovery must confirm
    # that the worker is old enough and clear its orphaned lock transactionally.
    with pytest.raises(MediaAssetBusy, match="video analysis"):
        media.delete("owner-a", asset_id)

    WorkerEngine(repository.tasks, clock=lambda: now)._recover_interrupted()

    analysis = repository.get("owner-a", UUID(accepted["analysis_id"]))
    assert analysis is not None
    assert analysis["status"] == "failed"
    assert analysis["error_code"] == "worker_interrupted"
    assert repository.load_for_worker(task_id) is None
    recovered_task = repository.tasks.get(task_id)
    assert recovered_task is not None
    assert recovered_task.status.value == "failed"
    with repository.tasks._connection() as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM media_asset_analysis_leases WHERE task_id = ?",
            (str(task_id),),
        ).fetchone()[0] == 0

    assert media.delete("owner-a", asset_id) == [str(asset["storage_key"])]
    assert media.cleanup_pending_files("owner-a") == 0


def test_active_analysis_limits_allow_idempotent_replay_but_reject_new_jobs(
    tmp_path, monkeypatch
):
    monkeypatch.setenv(
        "MRH_WORKFLOW_PAYLOAD_KEY",
        base64.urlsafe_b64encode(b"c" * 32).decode("ascii"),
    )
    from mrhub.video_intelligence import jobs as video_jobs

    monkeypatch.setattr(video_jobs, "MAX_ACTIVE_VIDEO_ANALYSES_PER_OWNER", 1)
    repository = _repository(tmp_path)
    request = _request("2c83d1c5-1d8d-4c29-8a3d-4dd0e0b10a00")

    accepted, created = repository.submit("owner-a", request, "active-cap-1")
    assert created is True

    replay, replay_created = repository.submit("owner-a", request, "active-cap-1")
    assert replay_created is False
    assert replay["analysis_id"] == accepted["analysis_id"]

    with pytest.raises(video_jobs.VideoAnalysisCapacityExceeded):
        repository.submit("owner-a", request, "active-cap-2")


def test_global_analysis_limit_applies_across_owners(tmp_path, monkeypatch):
    monkeypatch.setenv(
        "MRH_WORKFLOW_PAYLOAD_KEY",
        base64.urlsafe_b64encode(b"d" * 32).decode("ascii"),
    )
    from mrhub.video_intelligence import jobs as video_jobs

    monkeypatch.setattr(video_jobs, "MAX_ACTIVE_VIDEO_ANALYSES_GLOBAL", 1)
    repository = _repository(tmp_path)
    request = _request("2c83d1c5-1d8d-4c29-8a3d-4dd0e0b10a00")

    repository.submit("owner-a", request, "global-cap-owner-a")
    with pytest.raises(video_jobs.VideoAnalysisCapacityExceeded):
        repository.submit("owner-b", request, "global-cap-owner-b")


def test_idempotent_replay_does_not_require_reencrypting_payload(tmp_path, monkeypatch):
    monkeypatch.setenv(
        "MRH_WORKFLOW_PAYLOAD_KEY",
        base64.urlsafe_b64encode(b"e" * 32).decode("ascii"),
    )
    repository = _repository(tmp_path)
    request = _request("2c83d1c5-1d8d-4c29-8a3d-4dd0e0b10a00")
    accepted, created = repository.submit("owner-a", request, "replay-without-key")
    assert created is True

    monkeypatch.delenv("MRH_WORKFLOW_PAYLOAD_KEY", raising=False)
    from types import SimpleNamespace

    from mrhub.jobs import payload_envelope

    monkeypatch.setattr(
        payload_envelope,
        "get_settings",
        lambda: SimpleNamespace(workflow_payload_key=None),
    )
    replay, replay_created = repository.submit(
        "owner-a", request, "replay-without-key"
    )
    assert replay_created is False
    assert replay["analysis_id"] == accepted["analysis_id"]


def test_cancel_queued_analysis_is_atomic_and_purges_encrypted_payload(tmp_path, monkeypatch):
    monkeypatch.setenv(
        "MRH_WORKFLOW_PAYLOAD_KEY",
        base64.urlsafe_b64encode(b"c" * 32).decode("ascii"),
    )
    repository = _repository(tmp_path)
    accepted, _ = repository.submit(
        "owner-a",
        _request("2c83d1c5-1d8d-4c29-8a3d-4dd0e0b10a00"),
        "cancel-queued",
    )
    analysis_id = UUID(accepted["analysis_id"])
    task_id = UUID(accepted["task_id"])

    result = repository.cancel("owner-a", analysis_id)

    assert result == {
        "analysis_id": str(analysis_id),
        "status": "cancelled",
        "cancellation_requested": False,
    }
    assert repository.get("owner-a", analysis_id)["status"] == "cancelled"
    assert repository.load_for_worker(task_id) is None
    assert repository.tasks.get(task_id).status.value == "cancelled"
    assert repository.cancel("owner-b", analysis_id) is None


def test_cancel_running_analysis_blocks_late_success_and_finishes_cancelled(tmp_path, monkeypatch):
    monkeypatch.setenv(
        "MRH_WORKFLOW_PAYLOAD_KEY",
        base64.urlsafe_b64encode(b"r" * 32).decode("ascii"),
    )
    repository = _repository(tmp_path)
    accepted, _ = repository.submit(
        "owner-a",
        _request("2c83d1c5-1d8d-4c29-8a3d-4dd0e0b10a00"),
        "cancel-running",
    )
    analysis_id = UUID(accepted["analysis_id"])
    task_id = UUID(accepted["task_id"])
    lease_expiry = "2099-01-01T00:00:00+00:00"
    with repository.tasks._connection() as connection:
        connection.execute(
            "UPDATE tasks SET status = 'running' WHERE task_id = ?",
            (str(task_id),),
        )
        connection.execute(
            """INSERT INTO worker_executions (
                task_id, lease_owner, lease_expires_at, execution_token
            ) VALUES (?, ?, ?, ?)""",
            (str(task_id), "worker-b", lease_expiry, 2),
        )
    lease = WorkerLease(
        task_id=str(task_id), owner="worker-b",
        fencing_token=2, expires_at=lease_expiry,
    )
    assert repository.mark_running(task_id, "owner-a", lease=lease)

    requested = repository.cancel("owner-a", analysis_id)
    assert requested["cancellation_requested"] is True
    assert requested["status"] == "running"
    assert repository.tasks.get(task_id).status.value == "cancelled"

    repository.finish(
        task_id, "owner-a", status="completed",
        result={"unexpected": True}, lease=lease,
    )
    assert repository.get("owner-a", analysis_id)["status"] == "running"
    assert repository.load_for_worker(task_id) is not None

    repository.finish(
        task_id, "owner-a", status="cancelled",
        error_code="cancelled_by_owner", lease=lease,
    )
    assert repository.get("owner-a", analysis_id)["status"] == "cancelled"
    assert repository.load_for_worker(task_id) is None
    with repository.tasks._connection() as connection:
        idempotency = connection.execute(
            "SELECT status FROM idempotency_records WHERE task_id = ?",
            (str(task_id),),
        ).fetchone()
    assert idempotency["status"] == "failed"


def test_cancel_analysis_is_idempotent_and_owner_scoped(tmp_path, monkeypatch):
    monkeypatch.setenv(
        "MRH_WORKFLOW_PAYLOAD_KEY",
        base64.urlsafe_b64encode(b"o" * 32).decode("ascii"),
    )
    repository = _repository(tmp_path)
    accepted, _ = repository.submit(
        "owner-a",
        _request("2c83d1c5-1d8d-4c29-8a3d-4dd0e0b10a00"),
        "cancel-owner-scope",
    )
    analysis_id = UUID(accepted["analysis_id"])
    assert repository.cancel("owner-b", analysis_id) is None
    first = repository.cancel("owner-a", analysis_id)
    second = repository.cancel("owner-a", analysis_id)
    assert first == second
    assert second["status"] == "cancelled"



def test_worker_failure_path_acknowledges_cancelled_task_instead_of_marking_failed():
    from types import SimpleNamespace
    from uuid import uuid4

    from mrhub.video_intelligence.worker import VideoAnalysisWorkerHandler

    calls = {}

    class FakeTasks:
        def get(self, _task_id):
            return SimpleNamespace(status=TaskStatus.CANCELLED)

    class FakeJobs:
        def finish(self, task_id, owner_user_id, **kwargs):
            calls.update({
                "task_id": task_id,
                "owner_user_id": owner_user_id,
                **kwargs,
            })

    handler = VideoAnalysisWorkerHandler.__new__(VideoAnalysisWorkerHandler)
    handler.tasks = FakeTasks()
    handler.jobs = FakeJobs()
    task = SimpleNamespace(task_id=uuid4())
    lease = SimpleNamespace(task_id=str(task.task_id))

    result = handler._fail(task, "owner-a", lease, "ffmpeg_failed")

    assert result == {"status": "cancelled"}
    assert calls["status"] == "cancelled"
    assert calls["error_code"] == "cancelled_by_owner"
