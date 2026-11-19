"""Provider-neutral contracts for explicit video generation handoff.

No adapter is registered by default. This module deliberately performs no network,
subprocess, model download, billing, or rendering operation.
"""
from __future__ import annotations

from enum import StrEnum
from typing import Annotated, BinaryIO, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator


class VideoGenerationSubmissionError(RuntimeError):
    """Provider submission may have reached the remote service; reconcile, never replay."""


class GenerationStatus(StrEnum):
    ACCEPTED = "accepted"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    UNKNOWN_OUTCOME = "unknown_outcome"


class VideoGenerationRequest(BaseModel):
    """Bounded request passed only after an explicit user generation action."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    prompt: str = Field(min_length=1, max_length=20_000)
    aspect_ratio: str = Field(pattern=r"^(9:16|16:9|1:1|4:5)$")
    duration_seconds: int = Field(ge=3, le=60)
    resolution: str = Field(default="720p", pattern=r"^(720p|1080p)$")
    remote_processing_approved: bool = Field(default=False, strict=True)
    remote_spend_approved: bool = Field(default=False, strict=True)
    max_remote_cost_usd: float = Field(default=0, ge=0, le=10_000, allow_inf_nan=False)
    idempotency_key: str = Field(min_length=1, max_length=255)


class VideoGenerationSubmission(BaseModel):
    """Opaque provider job reference; never contains provider credentials."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: str = Field(min_length=1, max_length=80)
    model: str = Field(min_length=1, max_length=120)
    provider_job_id: str = Field(min_length=1, max_length=255)
    status: GenerationStatus
    progress_percent: int | None = Field(default=None, ge=0, le=100)


class VideoGenerationResult(BaseModel):
    """Provider result metadata; output bytes must be fetched through a bounded adapter."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: str = Field(min_length=1, max_length=80)
    model: str = Field(min_length=1, max_length=120)
    provider_job_id: str = Field(min_length=1, max_length=255)
    status: GenerationStatus
    output_bytes: int | None = Field(default=None, ge=1, le=100_000_000)
    duration_seconds: float | None = Field(default=None, gt=0, le=60)
    width: int | None = Field(default=None, ge=1, le=3840)
    height: int | None = Field(default=None, ge=1, le=3840)
    error_code: str | None = Field(
        default=None,
        max_length=80,
        pattern=r"^[a-z0-9][a-z0-9_.-]{0,79}$",
    )

    @model_validator(mode="after")
    def validate_terminal_result(self) -> VideoGenerationResult:
        if self.status is GenerationStatus.SUCCEEDED and any(
            value is None
            for value in (
                self.output_bytes,
                self.duration_seconds,
                self.width,
                self.height,
            )
        ):
            raise ValueError("Successful generation requires bounded output metadata")
        if self.status is GenerationStatus.FAILED and not self.error_code:
            raise ValueError("Failed generation requires a stable error code")
        return self


class VideoGenerationCapability(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)

    provider: str = Field(min_length=1, max_length=80)
    model: str = Field(min_length=1, max_length=120)
    local: bool
    supported_aspect_ratios: tuple[
        Annotated[str, Field(pattern=r"^(9:16|16:9|1:1|4:5)$")], ...
    ] = Field(min_length=1)
    max_duration_seconds: int = Field(ge=3, le=60)
    max_resolution: str = Field(pattern=r"^(720p|1080p)$")
    # Missing local resource requirements are treated as unknown by the router.
    required_memory_gb: float | None = Field(default=None, ge=0)
    required_vram_gb: float = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_capability(self) -> VideoGenerationCapability:
        if len(set(self.supported_aspect_ratios)) != len(self.supported_aspect_ratios):
            raise ValueError("Provider aspect ratios must be unique")
        return self




class VideoGenerationCostEstimator(Protocol):
    """Optional side-effect-free cost estimator for read-only route previews."""

    def estimate_cost_usd(self, request: VideoGenerationRequest) -> float | None:
        """Return a local estimate only; never contact a provider or reserve/bill."""
        ...


class VideoGenerationProvider(Protocol):
    """Adapter contract. Implementations must bound time, bytes, and remote effects."""

    @property
    def capability(self) -> VideoGenerationCapability:
        ...

    def submit(self, request: VideoGenerationRequest) -> VideoGenerationSubmission:
        """Submit exactly once using the supplied idempotency key."""
        ...

    def get_status(self, provider_job_id: str) -> VideoGenerationResult:
        ...

    def find_by_idempotency_key(
        self, idempotency_key: str
    ) -> VideoGenerationSubmission | None:
        """Find an earlier submission without creating or replaying a request.

        This lookup is required to recover a provider job reference when submit()
        may have succeeded remotely but its response was lost. Return a submission
        only when it is authoritatively associated with this exact key. Return None
        when no matching submission is currently discoverable; callers must keep
        the local job in unknown_outcome and must never infer that resubmission is
        safe. Lookup timeouts and provider errors must raise and remain ambiguous.
        """
        ...

    def download_output(
        self,
        provider_job_id: str,
        sink: BinaryIO,
        *,
        max_bytes: int,
    ) -> int:
        """Stream output into a caller-owned bounded sink; never return or fetch a raw URL.

        The application supplies a sink that rejects writes above max_bytes. The
        adapter must not close the sink and must return the exact byte count written.
        """
        ...

    def cancel(self, provider_job_id: str) -> bool:
        """Idempotently request provider-side cancellation for an existing job.

        True means the provider accepted the cancellation request; False means it
        could not accept a new request (for example, the job is already terminal).
        Callers must still confirm the final outcome through get_status().
        """
        ...
