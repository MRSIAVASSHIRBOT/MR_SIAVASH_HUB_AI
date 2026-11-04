import base64
from uuid import UUID, uuid4

import pytest

from mrhub.domain.tasks import TaskRecord, TaskStatus
from mrhub.video_intelligence.generation import (
    GenerationStatus,
    VideoGenerationRequest,
    VideoGenerationResult,
)
from mrhub.video_intelligence.generation_jobs import (
    VideoGenerationConflict,
    VideoGenerationJobRepository,
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
    from types import SimpleNamespace

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
