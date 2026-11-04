"""Lease-fenced provider submission and explicit outcome reconciliation."""
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
    """Submit once; reconcile ambiguous outcomes only through provider lookup."""

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
        job_status = str(loaded["status"])

        if lease_lost.is_set():
            return {"generation_id": str(generation_id), "status": "lease_lost"}
        try:
            provider = video_generation_registry.get(provider_name, model_name)
        except LookupError:
            if job_status == "queued":
                self.jobs.transition_under_lease(
                    owner, generation_id, "failed", lease=lease,
                    error_code="provider_unavailable",
                )
            raise ValueError("Generation provider is unavailable") from None

        capability = provider.capability
        if (capability.provider, capability.model) != (provider_name, model_name):
            if job_status == "queued":
                self.jobs.transition_under_lease(
                    owner, generation_id, "failed", lease=lease,
                    error_code="provider_capability_mismatch",
                )
                raise ValueError("Configured provider capability changed")
            raise ValueError("provider_capability_changed_during_reconciliation")

        request_data = dict(loaded["request"])
        request_data["idempotency_key"] = str(generation_id)
        request = VideoGenerationRequest.model_validate(request_data)
        if (
            request.duration_seconds > capability.max_duration_seconds
            or request.resolution not in {"720p", "1080p"}
            or (request.resolution == "1080p" and capability.max_resolution != "1080p")
            or request.aspect_ratio not in capability.supported_aspect_ratios
        ):
            if job_status == "queued":
                self.jobs.transition_under_lease(
                    owner, generation_id, "failed", lease=lease,
                    error_code="provider_capability_mismatch",
                )
                raise ValueError("Generation request exceeds provider capability")
            raise ValueError("provider_capability_changed_during_reconciliation")

        if job_status == "queued":
            return self._submit_once(
                provider, request, provider_name, model_name, owner,
                generation_id, lease, lease_lost,
            )
        if job_status not in {"unknown_outcome", "running"}:
            raise ValueError("Generation job is not eligible for reconciliation")
        return self._reconcile(
            provider, provider_name, model_name, owner, generation_id,
            loaded.get("provider_job_id"), lease, lease_lost,
        )

    def _submit_once(
        self,
        provider,
        request: VideoGenerationRequest,
        provider_name: str,
        model_name: str,
        owner: str,
        generation_id: UUID,
        lease: WorkerLease,
        lease_lost: Event,
    ) -> dict[str, object]:
        self.jobs.transition_under_lease(
            owner, generation_id, "submitting", lease=lease
        )
        if lease_lost.is_set():
            return {"generation_id": str(generation_id), "status": "lease_lost"}

        try:
            submission = provider.submit(request)
        except Exception:  # noqa: BLE001 - an adapter failure can follow a remote side effect
            if not lease_lost.is_set():
                self.jobs.transition_under_lease(
                    owner, generation_id, "unknown_outcome", lease=lease,
                    error_code="provider_submission_outcome_unknown",
                )
            raise ValueError("provider_submission_outcome_unknown") from None

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
            raise ValueError("provider_submission_identity_mismatch")
        if submission.status is GenerationStatus.UNKNOWN_OUTCOME:
            self.jobs.transition_under_lease(
                owner, generation_id, "unknown_outcome", lease=lease,
                provider_job_id=submission.provider_job_id,
                error_code="provider_reported_unknown_outcome",
            )
            raise ValueError("provider_reported_unknown_outcome")
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
            progress_percent=submission.progress_percent,
        )
        return {
            "generation_id": str(generation_id),
            "status": "running",
            "provider_job_id": submission.provider_job_id,
        }

    def _reconcile(
        self,
        provider,
        provider_name: str,
        model_name: str,
        owner: str,
        generation_id: UUID,
        provider_job_id: object,
        lease: WorkerLease,
        lease_lost: Event,
    ) -> dict[str, object]:
        """Find an ambiguous submission by its original key; never call submit here."""
        if not provider_job_id:
            try:
                submission = provider.find_by_idempotency_key(str(generation_id))
            except Exception:  # noqa: BLE001 - lookup failure remains ambiguous
                raise ValueError("provider_reconciliation_lookup_failed") from None
            if submission is None:
                return {
                    "generation_id": str(generation_id),
                    "status": "unknown_outcome",
                    "reason_code": "provider_submission_not_discoverable",
                }
            if (
                submission.provider != provider_name
                or submission.model != model_name
                or not submission.provider_job_id
            ):
                raise ValueError("provider_reconciliation_identity_mismatch")
            if submission.status in {GenerationStatus.FAILED, GenerationStatus.CANCELLED}:
                self.jobs.transition_under_lease(
                    owner, generation_id, "failed", lease=lease,
                    provider_job_id=submission.provider_job_id,
                    error_code="provider_reconciled_terminal_failure",
                )
                return {"generation_id": str(generation_id), "status": "failed"}
            if submission.status is GenerationStatus.UNKNOWN_OUTCOME:
                self.jobs.transition_under_lease(
                    owner, generation_id, "unknown_outcome", lease=lease,
                    provider_job_id=submission.provider_job_id,
                    error_code="provider_reconciled_unknown_outcome",
                )
                return {"generation_id": str(generation_id), "status": "unknown_outcome"}
            provider_job_id = submission.provider_job_id
            self.jobs.transition_under_lease(
                owner, generation_id, "running", lease=lease,
                provider_job_id=str(provider_job_id),
                progress_percent=submission.progress_percent,
            )

        if lease_lost.is_set():
            return {"generation_id": str(generation_id), "status": "lease_lost"}
        provider_job_id = str(provider_job_id)
        try:
            result = provider.get_status(provider_job_id)
        except Exception:  # noqa: BLE001 - provider status failures are retryable
            raise ValueError("provider_status_lookup_failed") from None
        if (
            result.provider != provider_name
            or result.model != model_name
            or result.provider_job_id != provider_job_id
        ):
            raise ValueError("provider_status_identity_mismatch")
        if lease_lost.is_set():
            return {"generation_id": str(generation_id), "status": "lease_lost"}

        if result.status is GenerationStatus.SUCCEEDED:
            from mrhub.media.repository import MediaAssetRepository
            from mrhub.video_intelligence.generation_output import (
                download_and_register_generation_output,
            )

            asset = download_and_register_generation_output(
                provider,
                result,
                self.jobs,
                MediaAssetRepository(self.jobs.database_path),
                owner,
                generation_id,
                lease=lease,
            )
            return {
                "generation_id": str(generation_id),
                "status": "succeeded",
                "output_asset_id": str(asset["asset_id"]),
            }
        if result.status in {GenerationStatus.FAILED, GenerationStatus.CANCELLED}:
            self.jobs.transition_under_lease(
                owner, generation_id, "failed", lease=lease,
                provider_job_id=provider_job_id,
                error_code=result.error_code or "provider_generation_failed",
            )
            return {"generation_id": str(generation_id), "status": "failed"}
        if result.status is GenerationStatus.UNKNOWN_OUTCOME:
            self.jobs.transition_under_lease(
                owner, generation_id, "unknown_outcome", lease=lease,
                provider_job_id=provider_job_id,
                error_code="provider_status_unknown_outcome",
            )
            return {"generation_id": str(generation_id), "status": "unknown_outcome"}

        self.jobs.transition_under_lease(
            owner, generation_id, "running", lease=lease,
            provider_job_id=provider_job_id,
            progress_percent=result.progress_percent,
        )
        return {
            "generation_id": str(generation_id),
            "status": "running",
            "provider_job_id": provider_job_id,
            "progress_percent": result.progress_percent,
        }
