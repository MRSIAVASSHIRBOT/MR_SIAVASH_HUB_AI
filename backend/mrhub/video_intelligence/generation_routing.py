"""Deterministic, fail-closed routing policy for hybrid video generation.

This module makes no hardware probes, network calls, provider submissions, or billing
requests. Callers must supply a measured local-capacity snapshot and explicit
per-request remote-processing and spending consent.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from mrhub.video_intelligence.generation import (
    VideoGenerationCapability,
    VideoGenerationRequest,
)


class GenerationRoute(StrEnum):
    LOCAL = "local"
    HOSTED = "hosted"


class RoutingReason(StrEnum):
    SELECTED_LOCAL = "selected_local"
    SELECTED_HOSTED = "selected_hosted"
    NO_COMPATIBLE_PROVIDER = "no_compatible_provider"
    LOCAL_CAPACITY_UNKNOWN = "local_capacity_unknown"
    LOCAL_CAPACITY_INSUFFICIENT = "local_capacity_insufficient"
    REMOTE_CONSENT_REQUIRED = "remote_consent_required"
    REMOTE_COST_UNKNOWN = "remote_cost_unknown"
    REMOTE_BUDGET_EXCEEDED = "remote_budget_exceeded"


class LocalCapacitySnapshot(BaseModel):
    """Measured capacity from the host running the local adapter; never client supplied."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    available: bool
    available_memory_gb: float | None = Field(default=None, ge=0)
    available_vram_gb: float | None = Field(default=None, ge=0)


class HybridRoutingPolicy(BaseModel):
    """Per-request policy. Remote work is denied unless both consents are explicit."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    remote_processing_approved: bool = False
    remote_spend_approved: bool = False
    max_remote_cost_usd: float = Field(default=0, ge=0, le=10_000)
    prefer_local: bool = True


@dataclass(frozen=True)
class GenerationRouteCandidate:
    capability: VideoGenerationCapability
    required_memory_gb: float = 0
    required_vram_gb: float = 0
    estimated_cost_usd: float | None = None

    def __post_init__(self) -> None:
        if self.required_memory_gb < 0 or self.required_vram_gb < 0:
            raise ValueError("Required local resources cannot be negative")
        if self.estimated_cost_usd is not None and self.estimated_cost_usd < 0:
            raise ValueError("Estimated provider cost cannot be negative")


class GenerationRouteDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    selected: bool
    route: GenerationRoute | None = None
    provider: str | None = None
    model: str | None = None
    estimated_cost_usd: float | None = None
    reason: RoutingReason


def _supports_request(
    capability: VideoGenerationCapability, request: VideoGenerationRequest
) -> bool:
    return (
        request.duration_seconds <= capability.max_duration_seconds
        and request.aspect_ratio in capability.supported_aspect_ratios
        and (
            request.resolution != "1080p"
            or capability.max_resolution == "1080p"
        )
    )


def _local_capacity_reason(
    candidate: GenerationRouteCandidate, capacity: LocalCapacitySnapshot
) -> RoutingReason | None:
    if not capacity.available:
        return RoutingReason.LOCAL_CAPACITY_INSUFFICIENT
    if capacity.available_memory_gb is None:
        return RoutingReason.LOCAL_CAPACITY_UNKNOWN
    if capacity.available_memory_gb < candidate.required_memory_gb:
        return RoutingReason.LOCAL_CAPACITY_INSUFFICIENT
    if candidate.required_vram_gb:
        if capacity.available_vram_gb is None:
            return RoutingReason.LOCAL_CAPACITY_UNKNOWN
        if capacity.available_vram_gb < candidate.required_vram_gb:
            return RoutingReason.LOCAL_CAPACITY_INSUFFICIENT
    return None


def choose_hybrid_route(
    candidates: list[GenerationRouteCandidate],
    request: VideoGenerationRequest,
    capacity: LocalCapacitySnapshot,
    policy: HybridRoutingPolicy,
) -> GenerationRouteDecision:
    """Choose local first, then consented and budget-bounded hosted fallback.

    Unknown local capacity is never treated as sufficient. Unknown hosted pricing is
    never treated as free. A route decision does not start or enqueue generation.
    """
    compatible = [
        item for item in candidates if _supports_request(item.capability, request)
    ]
    local_candidates = [item for item in compatible if item.capability.local]
    hosted_candidates = [item for item in compatible if not item.capability.local]

    local_block_reasons: list[RoutingReason] = []
    for candidate in local_candidates:
        reason = _local_capacity_reason(candidate, capacity)
        if reason is None:
            return GenerationRouteDecision(
                selected=True,
                route=GenerationRoute.LOCAL,
                provider=candidate.capability.provider,
                model=candidate.capability.model,
                estimated_cost_usd=0,
                reason=RoutingReason.SELECTED_LOCAL,
            )
        local_block_reasons.append(reason)

    if hosted_candidates:
        if not (
            policy.remote_processing_approved and policy.remote_spend_approved
        ):
            return GenerationRouteDecision(
                selected=False,
                reason=RoutingReason.REMOTE_CONSENT_REQUIRED,
            )
        priced = [
            item for item in hosted_candidates
            if item.estimated_cost_usd is not None
        ]
        if not priced:
            return GenerationRouteDecision(
                selected=False,
                reason=RoutingReason.REMOTE_COST_UNKNOWN,
            )
        affordable = [
            item for item in priced
            if item.estimated_cost_usd <= policy.max_remote_cost_usd
        ]
        if not affordable:
            return GenerationRouteDecision(
                selected=False,
                reason=RoutingReason.REMOTE_BUDGET_EXCEEDED,
            )
        chosen = min(
            affordable,
            key=lambda item: (
                item.estimated_cost_usd,
                item.capability.provider,
                item.capability.model,
            ),
        )
        return GenerationRouteDecision(
            selected=True,
            route=GenerationRoute.HOSTED,
            provider=chosen.capability.provider,
            model=chosen.capability.model,
            estimated_cost_usd=chosen.estimated_cost_usd,
            reason=RoutingReason.SELECTED_HOSTED,
        )

    if local_block_reasons:
        reason = (
            RoutingReason.LOCAL_CAPACITY_UNKNOWN
            if RoutingReason.LOCAL_CAPACITY_UNKNOWN in local_block_reasons
            else RoutingReason.LOCAL_CAPACITY_INSUFFICIENT
        )
        return GenerationRouteDecision(selected=False, reason=reason)
    return GenerationRouteDecision(
        selected=False, reason=RoutingReason.NO_COMPATIBLE_PROVIDER
    )
