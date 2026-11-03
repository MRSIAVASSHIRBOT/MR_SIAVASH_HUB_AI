import base64
from uuid import UUID, uuid4

import pytest

from mrhub.domain.tasks import TaskRecord
from mrhub.video_intelligence.generation import (
    GenerationStatus,
    VideoGenerationRequest,
    VideoGenerationResult,
)
from mrhub.video_intelligence.schemas import VideoTechnicalMetadata
from mrhub.video_intelligence.generation_jobs import (
    VideoGenerationConflict,
    VideoGenerationJobRepository,
)


def _repository(tmp_path):
    repository = VideoGenerationJobRepository(tmp_path / "generation.sqlite")
    repository.tasks.create_auth_user("owner-a", "owner-a", "salt-a", "hash-a")
    repository.tasks.create_auth_user("owner-b", "owner-b", "salt-b", "hash-b")
    task = TaskRecord(task_type="video.analysis", description="Completed source analysis")
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
