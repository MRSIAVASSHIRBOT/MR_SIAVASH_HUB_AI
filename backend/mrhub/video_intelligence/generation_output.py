"""Safe handoff from a completed provider job to a private media asset."""
from __future__ import annotations

from uuid import UUID

from mrhub.jobs.leases import WorkerLease
from mrhub.media.repository import MAX_OUTPUT_BYTES, MediaAssetRepository
from mrhub.video_intelligence.generation import (
    GenerationStatus,
    VideoGenerationProvider,
    VideoGenerationResult,
)
from mrhub.video_intelligence.generation_jobs import VideoGenerationJobRepository


def download_and_register_generation_output(
    provider: VideoGenerationProvider,
    result: VideoGenerationResult,
    jobs: VideoGenerationJobRepository,
    media: MediaAssetRepository,
    owner_user_id: str,
    generation_id: UUID,
    *,
    lease: WorkerLease | None = None,
) -> dict[str, object]:
    """Stream one successful result into bounded storage, then independently validate it.

    The adapter never chooses a destination path or returns a raw output URL.
    A mismatch between its reported count, the sink's byte count, and provider
    metadata aborts the temporary file before it can become visible.
    """
    if result.status is not GenerationStatus.SUCCEEDED:
        raise ValueError("Only successful generation results can be downloaded")
    capability = provider.capability
    if (capability.provider, capability.model) != (result.provider, result.model):
        raise ValueError("Provider capability does not match the generation result")
    job = jobs.get(owner_user_id, generation_id)
    if (
        job is None
        or job["status"] not in {"submitting", "running", "unknown_outcome"}
        or job["provider"] != result.provider
        or job["model"] != result.model
        or job["provider_job_id"] != result.provider_job_id
    ):
        raise ValueError("Provider result does not match an active owner-scoped generation job")

    asset_id, storage_key, output_path = media.new_output_target()
    with media.create_output_sink(storage_key, max_bytes=MAX_OUTPUT_BYTES) as sink:
        reported_bytes = provider.download_output(
            result.provider_job_id, sink, max_bytes=MAX_OUTPUT_BYTES
        )
        if (
            type(reported_bytes) is not int
            or reported_bytes <= 0
            or reported_bytes != sink.bytes_written
            or reported_bytes != result.output_bytes
        ):
            raise ValueError("Provider output byte count does not match the bounded sink")
        sink.commit()

    try:
        asset = jobs.complete_with_output(
            owner_user_id,
            generation_id,
            asset_id,
            storage_key,
            output_path,
            f"generated-{asset_id}.mp4",
            result,
            lease=lease,
        )
        if asset is None:
            raise ValueError("Generation job is unavailable for output registration")
        return asset
    except Exception:
        # The file is private and unreferenced unless finalization committed.
        # complete_with_output performs its asset/job writes in one transaction.
        output_path.unlink(missing_ok=True)
        raise
