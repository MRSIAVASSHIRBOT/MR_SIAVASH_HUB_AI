"""Lease-fenced provider submission for durable video-generation tasks."""
from __future__ import annotations

from threading import Event
from uuid import UUID

from mrhub.domain.tasks import TaskRecord
from mrhub.jobs.leases import WorkerLease
from mrhub.video_intelligence.generation import (
    GenerationStatus,
    VideoGenerationRequest,
)
from mrhub.video_intelligence.generation_jobs import VideoGenerationJobRepository
from mrhub.video_intelligence.generation_registry import video_generation_registry


class VideoGenerationWorkerHandler:
    """Submit each queued provider job once; ambiguous outcomes are never retried."""

    def __init__(self, repository) -> None:
        self.jobs = VideoGenerationJobRepository(repository.database_path)

    def __call__(
        self, task: TaskRecord, *, lease: WorkerLease, lease_lost: Event
    ) -> dict[str, object]:
        loaded = self.jobs.load_for_worker(task.task_id)
        if loaded is None:
            raise ValueError("Generation task payload is unavailable")
        owner = str(loaded["owner_user_id"])
        generation_id = UUID(str(loaded["generation_id"]))
        provider_name = str(loaded["provider"])
        model_name = str(loaded["model"])

        if lease_lost.is_set():
            return {"generation_id": str(generation_id), "status": "lease_lost"}
        try:
            provider = video_generation_registry.get(provider_name, model_name)
        except LookupError:
            self.jobs.transition_under_lease(
                owner, generation_id, "failed", lease=lease,
                error_code="provider_unavailable",
            )
            raise ValueError("Generation provider is unavailable")

        capability = provider.capability
        if (capability.provider, capability.model) != (provider_name, model_name):
            self.jobs.transition_under_lease(
                owner, generation_id, "failed", lease=lease,
                error_code="provider_capability_mismatch",
            )
            raise ValueError("Configured provider capability changed")

        request_data = dict(loaded["request"])
        request_data["idempotency_key"] = str(generation_id)
        request = VideoGenerationRequest.model_validate(request_data)
        if (
            request.duration_seconds > capability.max_duration_seconds
            or request.resolution not in {"720p", "1080p"}
            or request.resolution == "1080p" and capability.max_resolution != "1080p"
            or request.aspect_ratio not in capability.supported_aspect_ratios
        ):
            self.jobs.transition_under_lease(
                owner, generation_id, "failed", lease=lease,
                error_code="provider_capability_mismatch",
            )
            raise ValueError("Generation request exceeds provider capability")

        self.jobs.transition_under_lease(
            owner, generation_id, "submitting", lease=lease
        )
        if lease_lost.is_set():
            return {"generation_id": str(generation_id), "status": "lease_lost"}

        try:
            submission = provider.submit(request)
        except Exception:
            # Once submit was entered, the remote side effect may have happened.
            # Never resubmit automatically; retain the encrypted request for
            # a provider-specific reconciliation operation.
            if not lease_lost.is_set():
                self.jobs.transition_under_lease(
                    owner, generation_id, "unknown_outcome", lease=lease,
                    error_code="provider_submission_outcome_unknown",
                )
            return {
                "generation_id": str(generation_id),
                "status": "unknown_outcome",
            }

        if lease_lost.is_set():
            return {"generation_id": str(generation_id), "status": "lease_lost"}
        if (
            submission.provider != provider_name
            or submission.model != model_name
            or not submission.provider_job_id
        ):
            self.jobs.transition_under_lease(
                owner, generation_id, "unknown_outcome", lease=lease,
                error_code="provider_submission_identity_mismatch",
            )
            return {
                "generation_id": str(generation_id),
                "status": "unknown_outcome",
            }
        if submission.status is GenerationStatus.UNKNOWN_OUTCOME:
            self.jobs.transition_under_lease(
                owner, generation_id, "unknown_outcome", lease=lease,
                provider_job_id=submission.provider_job_id,
                error_code="provider_reported_unknown_outcome",
            )
            return {
                "generation_id": str(generation_id),
                "status": "unknown_outcome",
            }
        if submission.status in {GenerationStatus.FAILED, GenerationStatus.CANCELLED}:
            self.jobs.transition_under_lease(
                owner, generation_id, "failed", lease=lease,
                provider_job_id=submission.provider_job_id,
                error_code="provider_rejected_generation",
            )
            return {"generation_id": str(generation_id), "status": "failed"}

        self.jobs.transition_under_lease(
            owner, generation_id, "running", lease=lease,
            provider_job_id=submission.provider_job_id,
        )
        return {
            "generation_id": str(generation_id),
            "status": "running",
            "provider_job_id": submission.provider_job_id,
        }
