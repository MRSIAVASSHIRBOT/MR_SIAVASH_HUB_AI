import base64
from uuid import UUID, uuid4

import pytest

from mrhub.domain.tasks import TaskRecord
from mrhub.media.repository import MediaAssetRepository
from mrhub.video_intelligence.generation import (
    GenerationStatus,
    VideoGenerationCapability,
    VideoGenerationRequest,
    VideoGenerationResult,
)
from mrhub.video_intelligence.generation_jobs import VideoGenerationJobRepository
from mrhub.video_intelligence.generation_output import (
    download_and_register_generation_output,
)
from mrhub.video_intelligence.schemas import VideoTechnicalMetadata


class _Provider:
    capability = VideoGenerationCapability(
        provider="local",
        model="renderer-v1",
        local=True,
        supported_aspect_ratios=("9:16", "16:9"),
        max_duration_seconds=30,
        max_resolution="720p",
    )

    def __init__(self, content: bytes, reported_bytes: int | None = None):
        self.content = content
        self.reported_bytes = reported_bytes

    def submit(self, request):
        raise NotImplementedError

    def get_status(self, provider_job_id):
        raise NotImplementedError

    def download_output(self, provider_job_id, sink, *, max_bytes):
        sink.write(self.content)
        return len(self.content) if self.reported_bytes is None else self.reported_bytes

    def cancel(self, provider_job_id):
        return True


def _setup(tmp_path, monkeypatch):
    monkeypatch.setenv(
        "MRH_WORKFLOW_PAYLOAD_KEY",
        base64.urlsafe_b64encode(b"z" * 32).decode("ascii"),
    )
    jobs = VideoGenerationJobRepository(tmp_path / "generation.sqlite")
    jobs.tasks.create_auth_user("owner-a", "owner-a", "salt-a", "hash-a")
    task = TaskRecord(task_type="video.analysis", description="Completed analysis")
    jobs.tasks.create(task)
    analysis_id = uuid4()
    with jobs.tasks._connection() as connection:
        connection.execute(
            """INSERT INTO video_analysis_runs (
                analysis_id, task_id, owner_user_id, mode, status,
                result_json, error_code, created_at, updated_at
            ) VALUES (?, ?, ?, 'faithful_style_reconstruction', 'completed',
                      '{}', NULL, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)""",
            (str(analysis_id), str(task.task_id), "owner-a"),
        )
    request = VideoGenerationRequest(
        prompt="An original cinematic sequence.",
        aspect_ratio="9:16",
        duration_seconds=10,
        idempotency_key="generation-output-test",
    )
    accepted, _ = jobs.submit(
        "owner-a", analysis_id, "local", "renderer-v1", request
    )
    generation_id = UUID(accepted["generation_id"])
    jobs.transition("owner-a", generation_id, "queued")
    jobs.transition(
        "owner-a", generation_id, "submitting", provider_job_id="provider-job-1"
    )
    return jobs, MediaAssetRepository(jobs.database_path), generation_id


def _result(content):
    return VideoGenerationResult(
        provider="local",
        model="renderer-v1",
        provider_job_id="provider-job-1",
        status=GenerationStatus.SUCCEEDED,
        output_bytes=len(content),
        duration_seconds=10,
        width=720,
        height=1280,
    )


def test_provider_output_is_bounded_and_registered_as_private_asset(
    tmp_path, monkeypatch
):
    jobs, media, generation_id = _setup(tmp_path, monkeypatch)
    content = b"provider-output-fixture"
    from mrhub.video_intelligence import service

    monkeypatch.setattr(
        service,
        "probe_video",
        lambda _path: VideoTechnicalMetadata(
            duration_seconds=10,
            width=720,
            height=1280,
            metadata_status="available",
        ),
    )

    asset = download_and_register_generation_output(
        _Provider(content), _result(content), jobs, media,
        "owner-a", generation_id,
    )

    assert asset["owner_user_id"] == "owner-a"
    assert asset["media_type"] == "video/mp4"
    assert asset["processing_status"] == "processed"
    assert asset["processing_profile"] == "video_ai_generated"
    assert media.file_path(asset["storage_key"]).read_bytes() == content
    assert jobs.get("owner-a", generation_id)["status"] == "succeeded"


def test_provider_byte_count_mismatch_aborts_without_publishing_file(
    tmp_path, monkeypatch
):
    jobs, media, generation_id = _setup(tmp_path, monkeypatch)
    content = b"provider-output-fixture"

    with pytest.raises(ValueError, match="byte count"):
        download_and_register_generation_output(
            _Provider(content, reported_bytes=len(content) - 1),
            _result(content),
            jobs,
            media,
            "owner-a",
            generation_id,
        )

    assert jobs.get("owner-a", generation_id)["status"] == "submitting"
    assert list(media.storage_root.iterdir()) == []


def test_provider_capability_mismatch_is_rejected_before_download(
    tmp_path, monkeypatch
):
    jobs, media, generation_id = _setup(tmp_path, monkeypatch)
    content = b"provider-output-fixture"
    provider = _Provider(content)
    provider.capability = VideoGenerationCapability(
        provider="other",
        model="renderer-v1",
        local=True,
        supported_aspect_ratios=("9:16",),
        max_duration_seconds=30,
        max_resolution="720p",
    )

    with pytest.raises(ValueError, match="capability"):
        download_and_register_generation_output(
            provider, _result(content), jobs, media, "owner-a", generation_id
        )

    assert list(media.storage_root.iterdir()) == []
