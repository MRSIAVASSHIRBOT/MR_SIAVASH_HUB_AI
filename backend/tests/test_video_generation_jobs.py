import base64
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from mrhub.domain.tasks import TaskRecord, TaskStatus
from mrhub.video_intelligence.generation import (
    GenerationStatus,
    VideoGenerationRequest,
    VideoGenerationResult,
    VideoGenerationSubmission,
)
from mrhub.video_intelligence.generation_jobs import (
    VideoGenerationConflict,
    VideoGenerationJobRepository,
    VideoGenerationReconciliationCooldown,
)
from mrhub.video_intelligence.schemas import VideoTechnicalMetadata


def _repository(tmp_path):
    repository = VideoGenerationJobRepository(tmp_path / "generation.sqlite")
    repository.tasks.create_auth_user("owner-a", "owner-a", "salt-a", "hash-a")
    repository.tasks.create_auth_user("owner-b", "owner-b", "salt-b", "hash-b")
    task = TaskRecord(
        task_type="video.analysis",
        status=TaskStatus.SUCCEEDED,
        description="Completed source analysis",
    )
    repository.tasks.create(task)
    analysis_id = uuid4()
    with repository.tasks._connection() as connection:
        connection.execute(
            """INSERT INTO video_analysis_runs (
                analysis_id, task_id, owner_user_id, mode, status,
                result_json, error_code, created_at, updated_at
            ) VALUES (?, ?, ?, 'faithful_style_reconstruction', 'completed',
                      '{}', NULL, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)""",
            (str(analysis_id), str(task.task_id), "owner-a"),
        )
        connection.execute(
            "UPDATE tasks SET status = 'succeeded' WHERE task_id = ?",
            (str(task.task_id),),
        )
    return repository, analysis_id


def _request(key="generation-1", **overrides):
    values = {
        "prompt": "An original cinematic sequence with a clear visual arc.",
        "aspect_ratio": "9:16",
        "duration_seconds": 10,
        "resolution": "720p",
        "idempotency_key": key,
    }
    values.update(overrides)
    return VideoGenerationRequest(**values)


def test_generation_submit_is_encrypted_owner_scoped_and_idempotent(
    tmp_path, monkeypatch
):
    monkeypatch.setenv(
        "MRH_WORKFLOW_PAYLOAD_KEY",
        base64.urlsafe_b64encode(b"g" * 32).decode("ascii"),
    )
    repository, analysis_id = _repository(tmp_path)
    accepted, created = repository.submit(
        "owner-a", analysis_id, "local", "renderer-v1", _request()
    )
    assert created is True
    assert accepted["status"] == "prepared"
    assert accepted["execution"] == "not_started"

    replay, replay_created = repository.submit(
        "owner-a", analysis_id, "local", "renderer-v1", _request()
    )
    assert replay_created is False
    assert replay["generation_id"] == accepted["generation_id"]

    generation_id = UUID(accepted["generation_id"])
    assert repository.get("owner-b", generation_id) is None
    assert repository.get("owner-a", generation_id)["status"] == "prepared"

    handoff = repository.load_for_handoff("owner-a", generation_id)
    assert handoff["request"]["prompt"].startswith("An original")
    assert handoff["provider"] == "local"

    with repository.tasks._connection() as connection:
        payload_row = connection.execute(
            "SELECT ciphertext_b64 FROM video_generation_payloads WHERE generation_id = ?",
            (str(generation_id),),
        ).fetchone()
    assert "An original cinematic" not in payload_row["ciphertext_b64"]


def test_generation_idempotency_rejects_different_request_and_owner_scope(
    tmp_path, monkeypatch
):
    monkeypatch.setenv(
        "MRH_WORKFLOW_PAYLOAD_KEY",
        base64.urlsafe_b64encode(b"h" * 32).decode("ascii"),
    )
    repository, analysis_id = _repository(tmp_path)
    repository.submit("owner-a", analysis_id, "local", "renderer-v1", _request())
    with pytest.raises(VideoGenerationConflict):
        repository.submit(
            "owner-a", analysis_id, "local", "renderer-v1",
            _request(prompt="A materially different prompt"),
        )

    # The same key is independent for another owner; source ownership still applies.
    with pytest.raises(ValueError, match="completed source analysis owned"):
        repository.submit("owner-b", analysis_id, "local", "renderer-v1", _request())


def test_generation_requires_completed_owned_analysis_and_valid_transition(
    tmp_path, monkeypatch
):
    monkeypatch.setenv(
        "MRH_WORKFLOW_PAYLOAD_KEY",
        base64.urlsafe_b64encode(b"i" * 32).decode("ascii"),
    )
    repository, analysis_id = _repository(tmp_path)
    accepted, _ = repository.submit(
        "owner-a", analysis_id, "local", "renderer-v1", _request()
    )
    generation_id = UUID(accepted["generation_id"])

    with pytest.raises(ValueError, match="Invalid generation transition"):
        repository.transition("owner-a", generation_id, "succeeded")

    queued = repository.transition("owner-a", generation_id, "queued")
    assert queued["status"] == "queued"
    with pytest.raises(ValueError, match="Invalid generation transition"):
        repository.transition("owner-a", generation_id, "prepared")

    unknown = repository.transition(
        "owner-a", generation_id, "cancelled", error_code="cancelled_by_owner"
    )
    assert unknown["status"] == "cancelled"
    assert repository.load_for_handoff("owner-a", generation_id) is None


def test_unknown_outcome_retains_encrypted_payload_for_reconciliation(
    tmp_path, monkeypatch
):
    monkeypatch.setenv(
        "MRH_WORKFLOW_PAYLOAD_KEY",
        base64.urlsafe_b64encode(b"j" * 32).decode("ascii"),
    )
    repository, analysis_id = _repository(tmp_path)
    accepted, _ = repository.submit(
        "owner-a", analysis_id, "local", "renderer-v1", _request()
    )
    generation_id = UUID(accepted["generation_id"])
    repository.transition("owner-a", generation_id, "queued")
    repository.transition("owner-a", generation_id, "submitting")
    record = repository.transition(
        "owner-a", generation_id, "unknown_outcome", error_code="provider_timeout"
    )
    assert record["status"] == "unknown_outcome"
    with pytest.raises(ValueError, match="Only prepared generation jobs"):
        repository.load_for_handoff("owner-a", generation_id)
    reconciled = repository.load_for_reconciliation("owner-a", generation_id)
    assert reconciled["request"]["prompt"].startswith("An original")
    with repository.tasks._connection() as connection:
        row = connection.execute(
            "SELECT 1 FROM video_generation_payloads WHERE generation_id = ?",
            (str(generation_id),),
        ).fetchone()
    assert row is not None


def test_generation_payload_key_is_required(tmp_path, monkeypatch):

    from mrhub.jobs import payload_envelope

    monkeypatch.delenv("MRH_WORKFLOW_PAYLOAD_KEY", raising=False)
    monkeypatch.setattr(
        payload_envelope,
        "get_settings",
        lambda: SimpleNamespace(workflow_payload_key=None),
    )
    repository, analysis_id = _repository(tmp_path)
    with pytest.raises(ValueError, match="encryption key is not configured"):
        repository.submit(
            "owner-a", analysis_id, "local", "renderer-v1", _request()
        )



def test_successful_generation_registers_private_output_asset_atomically(
    tmp_path, monkeypatch
):
    monkeypatch.setenv(
        "MRH_WORKFLOW_PAYLOAD_KEY",
        base64.urlsafe_b64encode(b"o" * 32).decode("ascii"),
    )
    repository, analysis_id = _repository(tmp_path)
    accepted, _ = repository.submit(
        "owner-a", analysis_id, "local", "renderer-v1", _request()
    )
    generation_id = UUID(accepted["generation_id"])
    repository.transition("owner-a", generation_id, "queued")
    repository.transition(
        "owner-a", generation_id, "submitting", provider_job_id="provider-job-1"
    )
    repository.transition("owner-a", generation_id, "running", progress_percent=80)
    with pytest.raises(ValueError):
        repository.transition("owner-a", generation_id, "succeeded")

    from mrhub.media.repository import MediaAssetRepository
    from mrhub.video_intelligence import service

    media = MediaAssetRepository(repository.database_path)
    asset_id, storage_key, output_path = media.new_output_target()
    content = b"bounded mp4 test fixture"
    output_path.write_bytes(content)
    monkeypatch.setattr(
        service,
        "probe_video",
        lambda _path: VideoTechnicalMetadata(
            duration_seconds=10.0,
            width=720,
            height=1280,
            metadata_status="available",
        ),
    )
    result = VideoGenerationResult(
        provider="local",
        model="renderer-v1",
        provider_job_id="provider-job-1",
        status=GenerationStatus.SUCCEEDED,
        output_bytes=len(content),
        duration_seconds=10.0,
        width=720,
        height=1280,
    )
    asset = repository.complete_with_output(
        "owner-a", generation_id, asset_id, storage_key,
        output_path, "generated-video.mp4", result,
    )
    assert asset["asset_id"] == asset_id
    assert asset["owner_user_id"] == "owner-a"
    assert asset["processing_status"] == "processed"
    assert asset["processing_profile"] == "video_ai_generated"
    job = repository.get("owner-a", generation_id)
    assert job["status"] == "succeeded"
    assert job["output_asset_id"] == asset_id
    assert job["output_bytes"] == len(content)
    assert job["output_width"] == 720
    assert repository.load_for_handoff("owner-a", generation_id) is None

    replay = repository.complete_with_output(
        "owner-a", generation_id, asset_id, storage_key,
        output_path, "generated-video.mp4", result,
    )
    assert replay["asset_id"] == asset_id
    assert len(media.list_assets("owner-a")) == 1



def test_output_registration_rejects_provider_identity_mismatch(tmp_path, monkeypatch):
    monkeypatch.setenv(
        "MRH_WORKFLOW_PAYLOAD_KEY",
        base64.urlsafe_b64encode(b"q" * 32).decode("ascii"),
    )
    repository, analysis_id = _repository(tmp_path)
    accepted, _ = repository.submit(
        "owner-a", analysis_id, "local", "renderer-v1", _request()
    )
    generation_id = UUID(accepted["generation_id"])
    repository.transition("owner-a", generation_id, "queued")
    repository.transition(
        "owner-a", generation_id, "submitting", provider_job_id="provider-job-2"
    )
    repository.transition("owner-a", generation_id, "running")

    from mrhub.media.repository import MediaAssetRepository
    from mrhub.video_intelligence import service

    media = MediaAssetRepository(repository.database_path)
    asset_id, storage_key, output_path = media.new_output_target()
    output_path.write_bytes(b"video bytes")
    monkeypatch.setattr(
        service,
        "probe_video",
        lambda _path: VideoTechnicalMetadata(
            duration_seconds=10.0,
            width=720,
            height=1280,
            metadata_status="available",
        ),
    )
    result = VideoGenerationResult(
        provider="other-provider",
        model="renderer-v1",
        provider_job_id="provider-job-2",
        status=GenerationStatus.SUCCEEDED,
        output_bytes=11,
        duration_seconds=10.0,
        width=720,
        height=1280,
    )
    with pytest.raises(ValueError, match="Provider result does not match"):
        repository.complete_with_output(
            "owner-a", generation_id, asset_id, storage_key,
            output_path, "generated-video.mp4", result,
        )
    assert repository.get("owner-a", generation_id)["status"] == "running"
    assert media.get("owner-a", UUID(asset_id)) is None


def test_generation_task_waits_for_action_bound_owner_approval(tmp_path, monkeypatch):
    from datetime import UTC, datetime
    from uuid import uuid4

    from mrhub.domain.tasks import RiskClass, TaskStatus
    from mrhub.jobs.worker import WorkerEngine, action_fingerprint
    from mrhub.video_intelligence.generation_registry import video_generation_registry

    monkeypatch.setenv(
        "MRH_WORKFLOW_PAYLOAD_KEY",
        base64.urlsafe_b64encode(b"v" * 32).decode("ascii"),
    )
    repository, analysis_id = _repository(tmp_path)
    accepted, _ = repository.submit(
        "owner-a", analysis_id, "local", "renderer-v1", _request("approval-key")
    )
    generation_id = UUID(accepted["generation_id"])
    linked = repository.enqueue("owner-a", generation_id)
    task_id = UUID(linked["task_id"])
    task = repository.tasks.get(task_id)

    assert linked["created"] is True
    assert task.task_type == "video.generation"
    assert task.risk_class is RiskClass.HIGH
    assert task.status is TaskStatus.WAITING_APPROVAL

    provider_lookups = []
    monkeypatch.setattr(
        video_generation_registry,
        "get",
        lambda provider, model: provider_lookups.append((provider, model))
        or (_ for _ in ()).throw(LookupError("provider unavailable")),
    )
    worker = WorkerEngine(repository.tasks)
    assert worker.run_once() is None
    assert provider_lookups == []
    assert repository.tasks.get(task_id).status is TaskStatus.WAITING_APPROVAL

    now = datetime.now(UTC).isoformat()
    repository.tasks.record_task_approval(
        {
            "approval_id": str(uuid4()),
            "task_id": str(task_id),
            "decision": "approved",
            "approver_id": "owner-a",
            "action_fingerprint": action_fingerprint(task),
            "reason": "Owner approved this exact generation request",
            "created_at": now,
        },
        expected_status=TaskStatus.WAITING_APPROVAL,
        target_status=TaskStatus.QUEUED,
    )
    assert repository.tasks.get(task_id).status is TaskStatus.QUEUED

    worker.run_once()
    assert provider_lookups == [("local", "renderer-v1")]
    assert repository.get("owner-a", generation_id)["status"] == "failed"


def test_rejected_generation_never_dispatches_and_purges_encrypted_payload(
    tmp_path, monkeypatch
):
    from datetime import UTC, datetime
    from uuid import uuid4

    from mrhub.domain.tasks import RiskClass, TaskStatus
    from mrhub.jobs.worker import WorkerEngine, action_fingerprint
    from mrhub.video_intelligence.generation_registry import video_generation_registry

    monkeypatch.setenv(
        "MRH_WORKFLOW_PAYLOAD_KEY",
        base64.urlsafe_b64encode(b"w" * 32).decode("ascii"),
    )
    repository, analysis_id = _repository(tmp_path)
    accepted, _ = repository.submit(
        "owner-a", analysis_id, "local", "renderer-v1", _request("rejected-key")
    )
    generation_id = UUID(accepted["generation_id"])
    linked = repository.enqueue("owner-a", generation_id)
    task_id = UUID(linked["task_id"])
    task = repository.tasks.get(task_id)
    assert task.risk_class is RiskClass.HIGH
    now = datetime.now(UTC).isoformat()
    repository.tasks.record_task_approval(
        {
            "approval_id": str(uuid4()),
            "task_id": str(task_id),
            "decision": "rejected",
            "approver_id": "owner-a",
            "action_fingerprint": action_fingerprint(task),
            "reason": "Owner rejected this generation request",
            "created_at": now,
        },
        expected_status=TaskStatus.WAITING_APPROVAL,
        target_status=TaskStatus.REJECTED,
    )

    assert repository.reject_pending_task(task_id, "owner-a") is True
    assert repository.get("owner-a", generation_id)["status"] == "failed"
    with repository.tasks._connection() as connection:
        payload = connection.execute(
            "SELECT 1 FROM video_generation_payloads WHERE generation_id = ?",
            (str(generation_id),),
        ).fetchone()
    assert payload is None

    provider_lookups = []
    monkeypatch.setattr(
        video_generation_registry,
        "get",
        lambda provider, model: provider_lookups.append((provider, model)),
    )
    worker = WorkerEngine(repository.tasks)
    assert worker.run_once() is None
    assert provider_lookups == []
    assert repository.tasks.get(task_id).status is TaskStatus.REJECTED


@pytest.mark.parametrize("error_kind", ["contract", "unexpected"])
def test_ambiguous_provider_submission_is_never_retried(tmp_path, monkeypatch, error_kind):
    from datetime import UTC, datetime
    from types import SimpleNamespace
    from uuid import uuid4

    from mrhub.domain.tasks import TaskStatus
    from mrhub.jobs.worker import WorkerEngine, action_fingerprint
    from mrhub.video_intelligence.generation import VideoGenerationSubmissionError
    from mrhub.video_intelligence.generation_registry import video_generation_registry

    monkeypatch.setenv(
        "MRH_WORKFLOW_PAYLOAD_KEY",
        base64.urlsafe_b64encode(b"x" * 32).decode("ascii"),
    )
    repository, analysis_id = _repository(tmp_path)
    accepted, _ = repository.submit(
        "owner-a", analysis_id, "local", "renderer-v1", _request("unknown-outcome-key")
    )
    generation_id = UUID(accepted["generation_id"])
    linked = repository.enqueue("owner-a", generation_id)
    task_id = UUID(linked["task_id"])
    task = repository.tasks.get(task_id)
    now = datetime.now(UTC).isoformat()
    repository.tasks.record_task_approval(
        {
            "approval_id": str(uuid4()),
            "task_id": str(task_id),
            "decision": "approved",
            "approver_id": "owner-a",
            "action_fingerprint": action_fingerprint(task),
            "reason": "Approved for controlled provider adapter test",
            "created_at": now,
        },
        expected_status=TaskStatus.WAITING_APPROVAL,
        target_status=TaskStatus.QUEUED,
    )

    calls = []
    submission_error = (
        VideoGenerationSubmissionError("ambiguous")
        if error_kind == "contract"
        else RuntimeError("unexpected adapter failure")
    )
    provider = SimpleNamespace(
        capability=SimpleNamespace(
            provider="local",
            model="renderer-v1",
            max_duration_seconds=60,
            supported_aspect_ratios=["9:16"],
            max_resolution="1080p",
        ),
        submit=lambda _request: calls.append("submit")
        or (_ for _ in ()).throw(submission_error),
    )
    monkeypatch.setattr(
        video_generation_registry,
        "get",
        lambda _provider, _model: provider,
    )
    worker = WorkerEngine(repository.tasks)

    worker.run_once()

    assert calls == ["submit"]
    assert repository.get("owner-a", generation_id)["status"] == "unknown_outcome"
    assert repository.tasks.get(task_id).status is TaskStatus.FAILED
    with repository.tasks._connection() as connection:
        payload = connection.execute(
            "SELECT 1 FROM video_generation_payloads WHERE generation_id = ?",
            (str(generation_id),),
        ).fetchone()
    assert payload is not None

    assert worker.run_once() is None
    assert calls == ["submit"]


def test_worker_rejects_queued_generation_without_approval_before_provider_lookup(
    tmp_path, monkeypatch
):
    from mrhub.domain.tasks import TaskStatus
    from mrhub.jobs.worker import WorkerEngine
    from mrhub.video_intelligence.generation_registry import video_generation_registry

    monkeypatch.setenv(
        "MRH_WORKFLOW_PAYLOAD_KEY",
        base64.urlsafe_b64encode(b"y" * 32).decode("ascii"),
    )
    repository, analysis_id = _repository(tmp_path)
    accepted, _ = repository.submit(
        "owner-a", analysis_id, "local", "renderer-v1", _request("missing-approval-key")
    )
    generation_id = UUID(accepted["generation_id"])
    linked = repository.enqueue("owner-a", generation_id)
    task_id = UUID(linked["task_id"])
    with repository.tasks._connection() as connection:
        connection.execute(
            "UPDATE tasks SET status = 'queued' WHERE task_id = ?",
            (str(task_id),),
        )

    provider_lookups = []
    monkeypatch.setattr(
        video_generation_registry,
        "get",
        lambda provider, model: provider_lookups.append((provider, model)),
    )
    worker = WorkerEngine(repository.tasks)
    worker.run_once()

    assert provider_lookups == []
    assert repository.tasks.get(task_id).status is TaskStatus.FAILED
    assert repository.get("owner-a", generation_id)["status"] == "failed"
    with repository.tasks._connection() as connection:
        payload = connection.execute(
            "SELECT 1 FROM video_generation_payloads WHERE generation_id = ?",
            (str(generation_id),),
        ).fetchone()
    assert payload is None


def test_generation_reconciliation_requeues_original_task_without_duplicate_links(
    tmp_path, monkeypatch
):
    monkeypatch.setenv(
        "MRH_WORKFLOW_PAYLOAD_KEY",
        base64.urlsafe_b64encode(b"r" * 32).decode("ascii"),
    )
    repository, analysis_id = _repository(tmp_path)
    accepted, _ = repository.submit(
        "owner-a", analysis_id, "local", "renderer-v1", _request("reconcile-requeue")
    )
    generation_id = UUID(accepted["generation_id"])
    linked = repository.enqueue("owner-a", generation_id)
    task_id = UUID(linked["task_id"])

    with repository.tasks._connection() as connection:
        connection.execute(
            "UPDATE video_generation_jobs SET status = 'unknown_outcome' WHERE generation_id = ?",
            (str(generation_id),),
        )
        connection.execute(
            "UPDATE tasks SET status = 'failed' WHERE task_id = ?",
            (str(task_id),),
        )
        connection.execute(
            """INSERT INTO worker_executions (
                task_id, attempt_count, error_code, finished_at
            ) VALUES (?, 3, 'handler_failed', CURRENT_TIMESTAMP)""",
            (str(task_id),),
        )

    queued = repository.enqueue_reconciliation("owner-a", generation_id)
    assert queued == {
        "generation_id": str(generation_id),
        "task_id": str(task_id),
        "status": "queued",
        "created": True,
    }
    assert repository.tasks.get(task_id).status is TaskStatus.QUEUED
    with repository.tasks._connection() as connection:
        execution = connection.execute(
            "SELECT attempt_count, error_code, finished_at FROM worker_executions WHERE task_id = ?",
            (str(task_id),),
        ).fetchone()
    assert execution["attempt_count"] == 0
    assert execution["error_code"] is None
    assert execution["finished_at"] is None

    replay = repository.enqueue_reconciliation("owner-a", generation_id)
    assert replay["task_id"] == str(task_id)
    assert replay["created"] is False

    with repository.tasks._connection() as connection:
        connection.execute(
            "UPDATE video_generation_jobs SET status = 'running', provider_job_id = ? "
            "WHERE generation_id = ?",
            ("provider-job-77", str(generation_id)),
        )
        connection.execute(
            "UPDATE tasks SET status = 'succeeded' WHERE task_id = ?",
            (str(task_id),),
        )
    with pytest.raises(VideoGenerationReconciliationCooldown) as cooldown:
        repository.enqueue_reconciliation("owner-a", generation_id)
    assert cooldown.value.retry_after_seconds > 0

    # Simulate cooldown expiry without sleeping in the test suite.
    with repository.tasks._connection() as connection:
        connection.execute(
            """UPDATE video_generation_reconciliation_limits
               SET next_allowed_at = '2000-01-01T00:00:00+00:00'
               WHERE generation_id = ? AND owner_user_id = ?""",
            (str(generation_id), "owner-a"),
        )
    refreshed = repository.enqueue_reconciliation("owner-a", generation_id)
    assert refreshed["created"] is True
    assert refreshed["task_id"] == str(task_id)
    assert repository.get("owner-a", generation_id)["status"] == "running"

    with repository.tasks._connection() as connection:
        connection.execute(
            "UPDATE tasks SET status = 'cancelled' WHERE task_id = ?",
            (str(task_id),),
        )
    with repository.tasks._connection() as connection:
        connection.execute(
            """UPDATE video_generation_reconciliation_limits
               SET next_allowed_at = '2000-01-01T00:00:00+00:00'
               WHERE generation_id = ? AND owner_user_id = ?""",
            (str(generation_id), "owner-a"),
        )
    after_local_cancel = repository.enqueue_reconciliation("owner-a", generation_id)
    assert after_local_cancel["created"] is True
    assert after_local_cancel["status"] == "queued"
    assert repository.enqueue_reconciliation("owner-b", generation_id) is None


def test_worker_reconciles_unknown_submission_and_registers_completed_output(
    tmp_path, monkeypatch
):
    from datetime import UTC, datetime
    from types import SimpleNamespace
    from uuid import uuid4

    from mrhub.domain.tasks import TaskStatus
    from mrhub.jobs.worker import WorkerEngine, action_fingerprint
    from mrhub.media.repository import MediaAssetRepository
    from mrhub.video_intelligence import service
    from mrhub.video_intelligence.generation_registry import video_generation_registry

    monkeypatch.setenv(
        "MRH_WORKFLOW_PAYLOAD_KEY",
        base64.urlsafe_b64encode(b"s" * 32).decode("ascii"),
    )
    repository, analysis_id = _repository(tmp_path)
    accepted, _ = repository.submit(
        "owner-a", analysis_id, "local", "renderer-v1", _request("reconcile-worker")
    )
    generation_id = UUID(accepted["generation_id"])
    linked = repository.enqueue("owner-a", generation_id)
    task_id = UUID(linked["task_id"])
    task = repository.tasks.get(task_id)
    now = datetime.now(UTC).isoformat()
    repository.tasks.record_task_approval(
        {
            "approval_id": str(uuid4()),
            "task_id": str(task_id),
            "decision": "approved",
            "approver_id": "owner-a",
            "action_fingerprint": action_fingerprint(task),
            "reason": "Owner approved the original generation request",
            "created_at": now,
        },
        expected_status=TaskStatus.WAITING_APPROVAL,
        target_status=TaskStatus.QUEUED,
    )

    output_bytes = b"reconciled generated video bytes"
    calls = {"submit": 0, "find": [], "status": 0, "download": 0}

    class Provider:
        capability = SimpleNamespace(
            provider="local",
            model="renderer-v1",
            max_duration_seconds=60,
            supported_aspect_ratios=["9:16"],
            max_resolution="1080p",
        )

        def submit(self, _request):
            calls["submit"] += 1
            raise RuntimeError("remote accepted but response was lost")

        def find_by_idempotency_key(self, key):
            calls["find"].append(key)
            if len(calls["find"]) == 1:
                return None
            return VideoGenerationSubmission(
                provider="local",
                model="renderer-v1",
                provider_job_id="provider-job-reconciled",
                status=GenerationStatus.RUNNING,
                progress_percent=15,
            )

        def get_status(self, provider_job_id):
            assert provider_job_id == "provider-job-reconciled"
            calls["status"] += 1
            if calls["status"] == 1:
                return VideoGenerationResult(
                    provider="local",
                    model="renderer-v1",
                    provider_job_id=provider_job_id,
                    status=GenerationStatus.RUNNING,
                )
            return VideoGenerationResult(
                provider="local",
                model="renderer-v1",
                provider_job_id=provider_job_id,
                status=GenerationStatus.SUCCEEDED,
                output_bytes=len(output_bytes),
                duration_seconds=10.0,
                width=720,
                height=1280,
            )

        def download_output(self, provider_job_id, sink, *, max_bytes):
            assert provider_job_id == "provider-job-reconciled"
            assert max_bytes >= len(output_bytes)
            calls["download"] += 1
            sink.write(output_bytes)
            return len(output_bytes)

    provider = Provider()
    monkeypatch.setattr(video_generation_registry, "get", lambda *_args: provider)
    monkeypatch.setattr(
        service,
        "probe_video",
        lambda _path: VideoTechnicalMetadata(
            duration_seconds=10.0,
            width=720,
            height=1280,
            metadata_status="available",
        ),
    )
    worker = WorkerEngine(repository.tasks)

    def expire_reconciliation_cooldown() -> None:
        # Advance only the persisted cooldown; avoid real sleeps in this integration test.
        with repository.tasks._connection() as connection:
            connection.execute(
                """UPDATE video_generation_reconciliation_limits
                   SET next_allowed_at = '2000-01-01T00:00:00+00:00'
                   WHERE generation_id = ? AND owner_user_id = ?""",
                (str(generation_id), "owner-a"),
            )

    # First execution may have reached the remote service, so it becomes ambiguous.
    worker.run_once()
    assert repository.get("owner-a", generation_id)["status"] == "unknown_outcome"
    assert repository.tasks.get(task_id).status is TaskStatus.FAILED
    assert calls["submit"] == 1

    # Reconciliation must not decrypt the original prompt. It only needs the
    # stable generation key and the provider job reference.
    monkeypatch.setenv("MRH_WORKFLOW_PAYLOAD_KEY", "temporarily-unavailable")

    # Reconciliation must remain possible if the provider's current capability
    # catalog changes after the original request has already been accepted.
    provider.capability = SimpleNamespace(
        provider="local",
        model="renderer-v1",
        max_duration_seconds=5,
        supported_aspect_ratios=["16:9"],
        max_resolution="720p",
    )

    # A lookup miss is not proof that submission never happened. Keep the
    # ambiguous state and allow a later explicit reconciliation attempt.
    repository.enqueue_reconciliation("owner-a", generation_id)
    worker.run_once()
    assert repository.get("owner-a", generation_id)["status"] == "unknown_outcome"
    assert repository.tasks.get(task_id).status is TaskStatus.SUCCEEDED
    lookup_miss_result = worker.get_result(task_id)
    assert lookup_miss_result is not None
    assert lookup_miss_result["result"]["status"] == "unknown_outcome"
    assert "provider_job_id" not in lookup_miss_result["result"]
    assert calls["find"] == [str(generation_id)]
    assert calls["submit"] == 1

    # A later lookup finds the original provider job and polls it.
    expire_reconciliation_cooldown()
    repository.enqueue_reconciliation("owner-a", generation_id)
    worker.run_once()
    running = repository.get("owner-a", generation_id)
    assert running["status"] == "running"
    assert running["provider_job_id"] == "provider-job-reconciled"
    assert running["progress_percent"] == 15
    assert repository.tasks.get(task_id).status is TaskStatus.SUCCEEDED
    running_result = worker.get_result(task_id)
    assert running_result is not None
    assert running_result["result"]["status"] == "running"
    assert "provider_job_id" not in running_result["result"]
    assert calls["find"] == [str(generation_id), str(generation_id)]
    assert calls["submit"] == 1

    # A later explicit refresh polls the known provider job and safely imports output.
    expire_reconciliation_cooldown()
    repository.enqueue_reconciliation("owner-a", generation_id)
    worker.run_once()
    completed = repository.get("owner-a", generation_id)
    assert completed["status"] == "succeeded"
    assert completed["output_asset_id"]
    assert completed["output_bytes"] == len(output_bytes)
    completed_result = worker.get_result(task_id)
    assert completed_result is not None
    assert completed_result["result"]["status"] == "succeeded"
    assert "provider_job_id" not in completed_result["result"]
    assert calls["submit"] == 1
    assert calls["find"] == [str(generation_id), str(generation_id)]
    assert calls["status"] == 2
    assert calls["download"] == 1
    asset = MediaAssetRepository(repository.database_path).get(
        "owner-a", UUID(completed["output_asset_id"])
    )
    assert asset is not None
    assert asset["processing_profile"] == "video_ai_generated"


def test_interrupted_provider_submission_recovers_to_unknown_outcome_without_purging_payload(
    tmp_path, monkeypatch
):
    monkeypatch.setenv(
        "MRH_WORKFLOW_PAYLOAD_KEY",
        base64.urlsafe_b64encode(b"t" * 32).decode("ascii"),
    )
    repository, analysis_id = _repository(tmp_path)
    accepted, _ = repository.submit(
        "owner-a", analysis_id, "local", "renderer-v1",
        _request("crash-after-provider-acceptance"),
    )
    generation_id = UUID(accepted["generation_id"])
    linked = repository.enqueue("owner-a", generation_id)
    task_id = UUID(linked["task_id"])

    # Simulate a process crash after submit() may have reached the provider,
    # but before the worker persisted the provider job reference.
    with repository.tasks._connection() as connection:
        connection.execute(
            "UPDATE tasks SET status = 'running' WHERE task_id = ?",
            (str(task_id),),
        )
        connection.execute(
            """UPDATE video_generation_jobs
               SET status = 'submitting'
               WHERE generation_id = ? AND owner_user_id = ?""",
            (str(generation_id), "owner-a"),
        )
        connection.execute(
            """INSERT INTO worker_executions (
                task_id, attempt_count, started_at
            ) VALUES (?, 1, ?)""",
            (str(task_id), "2000-01-01T00:00:00+00:00"),
        )

    from mrhub.jobs.worker import WorkerEngine

    worker = WorkerEngine(repository.tasks)
    assert worker.run_once() is None

    recovered = repository.get("owner-a", generation_id)
    assert recovered["status"] == "unknown_outcome"
    assert recovered["error_code"] == "worker_interrupted_during_submission"
    assert repository.tasks.get(task_id).status is TaskStatus.FAILED

    reconciled = repository.load_for_reconciliation("owner-a", generation_id)
    assert reconciled["request"]["prompt"].startswith("An original")
    with repository.tasks._connection() as connection:
        payload = connection.execute(
            "SELECT 1 FROM video_generation_payloads WHERE generation_id = ?",
            (str(generation_id),),
        ).fetchone()
    assert payload is not None


@pytest.mark.parametrize("lookup_first", [False, True])
def test_provider_cancellation_uses_distinct_terminal_error_code(
    lookup_first: bool,
):
    from threading import Event

    from mrhub.jobs.leases import WorkerLease
    from mrhub.video_intelligence.generation_worker import VideoGenerationWorkerHandler

    generation_id = uuid4()
    calls = []

    class Jobs:
        def transition_under_lease(self, owner, requested_id, target, **kwargs):
            calls.append((owner, requested_id, target, kwargs))
            return {"status": target}

    class Provider:
        def find_by_idempotency_key(self, key):
            assert key == str(generation_id)
            return VideoGenerationSubmission(
                provider="local",
                model="renderer-v1",
                provider_job_id="provider-cancelled",
                status=GenerationStatus.CANCELLED,
            )

        def get_status(self, provider_job_id):
            assert provider_job_id == "provider-cancelled"
            return VideoGenerationResult(
                provider="local",
                model="renderer-v1",
                provider_job_id=provider_job_id,
                status=GenerationStatus.CANCELLED,
            )

    handler = VideoGenerationWorkerHandler.__new__(VideoGenerationWorkerHandler)
    handler.jobs = Jobs()
    provider = Provider()
    lease = WorkerLease(
        task_id=str(uuid4()),
        owner="worker-a",
        fencing_token=1,
        expires_at="2099-01-01T00:00:00+00:00",
    )
    result = handler._reconcile(
        provider,
        "local",
        "renderer-v1",
        "owner-a",
        generation_id,
        None if lookup_first else "provider-cancelled",
        lease,
        Event(),
    )

    assert result["status"] == "cancelled"
    assert len(calls) == 1
    assert calls[0][2] == "cancelled"
    assert calls[0][3]["error_code"] == "provider_generation_cancelled"


def test_reconciliation_cooldown_returns_http_429_and_retry_after(
    monkeypatch,
) -> None:
    from client_helpers import authenticated_client

    def reject_during_cooldown(self, owner_user_id, generation_id):
        raise VideoGenerationReconciliationCooldown(37)

    monkeypatch.setattr(
        VideoGenerationJobRepository,
        "enqueue_reconciliation",
        reject_during_cooldown,
    )
    client = authenticated_client()
    try:
        response = client.post(
            f"/video-intelligence/generations/{uuid4()}/reconcile"
        )
        assert response.status_code == 429
        assert response.headers["Retry-After"] == "37"
        assert response.json()["detail"]["code"] == "reconciliation_cooldown"
        assert response.json()["detail"]["retry_after_seconds"] == 37
    finally:
        client.close()


def test_concurrent_reconciliation_requests_create_one_active_attempt(
    tmp_path, monkeypatch
):
    from concurrent.futures import ThreadPoolExecutor

    monkeypatch.setenv(
        "MRH_WORKFLOW_PAYLOAD_KEY",
        base64.urlsafe_b64encode(b"c" * 32).decode("ascii"),
    )
    repository, analysis_id = _repository(tmp_path)
    accepted, _ = repository.submit(
        "owner-a",
        analysis_id,
        "local",
        "renderer-v1",
        _request("reconcile-concurrent"),
    )
    generation_id = UUID(accepted["generation_id"])
    linked = repository.enqueue("owner-a", generation_id)
    task_id = UUID(linked["task_id"])
    with repository.tasks._connection() as connection:
        connection.execute(
            "UPDATE video_generation_jobs SET status = 'unknown_outcome' WHERE generation_id = ?",
            (str(generation_id),),
        )
        connection.execute(
            "UPDATE tasks SET status = 'failed' WHERE task_id = ?",
            (str(task_id),),
        )

    def request_reconciliation():
        return repository.enqueue_reconciliation("owner-a", generation_id)

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: request_reconciliation(), range(2)))

    assert sum(bool(result["created"]) for result in results) == 1
    assert {result["task_id"] for result in results} == {str(task_id)}
    assert all(result["status"] == "queued" for result in results)
    with repository.tasks._connection() as connection:
        attempt = connection.execute(
            """SELECT attempt_count, next_allowed_at
               FROM video_generation_reconciliation_limits
               WHERE generation_id = ? AND owner_user_id = ?""",
            (str(generation_id), "owner-a"),
        ).fetchone()
    assert attempt["attempt_count"] == 1
    assert attempt["next_allowed_at"] is not None
