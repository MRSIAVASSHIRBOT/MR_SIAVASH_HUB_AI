"""Provider-neutral contracts for explicit video generation handoff.

No adapter is registered by default. This module deliberately performs no network,
subprocess, model download, billing, or rendering operation.
"""
from __future__ import annotations

from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field


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
    output_url: str | None = Field(default=None, max_length=2048)
    output_bytes: int | None = Field(default=None, ge=1, le=100_000_000)
    duration_seconds: float | None = Field(default=None, gt=0, le=60)
    width: int | None = Field(default=None, ge=1, le=3840)
    height: int | None = Field(default=None, ge=1, le=3840)
    error_code: str | None = Field(default=None, max_length=80)


class VideoGenerationCapability(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: str = Field(min_length=1, max_length=80)
    model: str = Field(min_length=1, max_length=120)
    local: bool
    supported_aspect_ratios: tuple[str, ...]
    max_duration_seconds: int = Field(ge=3, le=60)
    max_resolution: str = Field(pattern=r"^(720p|1080p)$")


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

    def cancel(self, provider_job_id: str) -> bool:
        ...
