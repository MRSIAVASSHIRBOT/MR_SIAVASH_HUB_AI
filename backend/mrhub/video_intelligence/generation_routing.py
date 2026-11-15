"""Deterministic, fail-closed routing policy for hybrid video generation.

`choose_hybrid_route` is a pure decision function: it makes no hardware probes,
network calls, provider submissions, or billing requests. The separate
`measure_local_capacity_snapshot` helper reads available RAM through existing
read-only host diagnostics. Callers must supply a trusted server-side snapshot and
explicit per-request remote-processing and spending consent.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from math import isfinite

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

    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)

    available: bool
    available_memory_gb: float | None = Field(default=None, ge=0)
    available_vram_gb: float | None = Field(default=None, ge=0)


def measure_local_capacity_snapshot() -> LocalCapacitySnapshot:
    """Read current worker RAM through the existing read-only host diagnostics.

    The diagnostics intentionally do not claim GPU VRAM: the current safe probe
    only lists adapter names. GPU-bound local candidates therefore remain blocked
    until a trusted VRAM probe is implemented.
    """
    from mrhub.diagnostics.hardware import collect_hardware_report

    report = collect_hardware_report()
    memory = report.get("memory", {})
    available_gib = memory.get("available_gib")
    return LocalCapacitySnapshot(
        available=available_gib is not None,
        available_memory_gb=available_gib,
        available_vram_gb=None,
    )


class HybridRoutingPolicy(BaseModel):
    """Per-request policy. Remote work is denied unless both consents are explicit."""

    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)

    remote_processing_approved: bool = False
    remote_spend_approved: bool = False
    max_remote_cost_usd: float = Field(default=0, ge=0, le=10_000)


@dataclass(frozen=True)
class GenerationRouteCandidate:
    capability: VideoGenerationCapability
    required_memory_gb: float | None = None
    required_vram_gb: float = 0
    estimated_cost_usd: float | None = None

    def __post_init__(self) -> None:
        resource_values = tuple(
            value for value in (self.required_memory_gb, self.required_vram_gb)
            if value is not None
        )
        if any(
            isinstance(value, bool) or not isfinite(value) or value < 0
            for value in resource_values
        ):
            raise ValueError("Required local resources must be finite and non-negative")
        if self.estimated_cost_usd is not None and (
            not isfinite(self.estimated_cost_usd) or self.estimated_cost_usd < 0
        ):
            raise ValueError("Estimated provider cost must be finite and non-negative")


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
    if candidate.required_memory_gb is None:
        return RoutingReason.LOCAL_CAPACITY_UNKNOWN
    if not capacity.available:
        return RoutingReason.LOCAL_CAPACITY_UNKNOWN
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
    for candidate in sorted(
        local_candidates,
        key=lambda item: (
            item.required_memory_gb if item.required_memory_gb is not None else float("inf"),
            item.required_vram_gb,
            item.capability.provider,
            item.capability.model,
        ),
    ):
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


class GenerationRoutePreviewRequest(BaseModel):
    """Bounded read-only route preview; this payload can never submit generation work."""

    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)

    duration_seconds: int = Field(ge=3, le=60, strict=True)
    aspect_ratio: str = Field(pattern=r"^(9:16|16:9|1:1|4:5)$")
    resolution: str = Field(default="720p", pattern=r"^(720p|1080p)$")
    remote_processing_approved: bool = Field(default=False, strict=True)
    remote_spend_approved: bool = Field(default=False, strict=True)
    max_remote_cost_usd: float = Field(default=0, ge=0, le=10_000)


def preview_hybrid_route(payload: GenerationRoutePreviewRequest) -> dict[str, object]:
    """Return a fail-closed route estimate without submitting or enqueueing a job."""
    from mrhub.video_intelligence.generation_registry import video_generation_registry

    request = VideoGenerationRequest(
        prompt="Read-only route preview",
        aspect_ratio=payload.aspect_ratio,
        duration_seconds=payload.duration_seconds,
        resolution=payload.resolution,
        idempotency_key="route-preview",
    )
    candidates: list[GenerationRouteCandidate] = []
    for capability in video_generation_registry.catalog():
        try:
            provider = video_generation_registry.get(capability.provider, capability.model)
        except LookupError:
            continue

        estimated_cost: float | None = None
        if not capability.local:
            estimator = getattr(provider, "estimate_cost_usd", None)
            if callable(estimator):
                try:
                    estimate = estimator(request)
                    if estimate is not None and not isinstance(estimate, bool):
                        candidate_cost = float(estimate)
                        if isfinite(candidate_cost) and candidate_cost >= 0:
                            estimated_cost = candidate_cost
                except Exception:  # noqa: BLE001 - unknown pricing must fail closed
                    estimated_cost = None

        try:
            candidates.append(GenerationRouteCandidate(
                capability=capability,
                required_memory_gb=capability.required_memory_gb,
                required_vram_gb=capability.required_vram_gb,
                estimated_cost_usd=estimated_cost,
            ))
        except (TypeError, ValueError):
            # Invalid adapter metadata is never promoted into an eligible route.
            continue

    if any(item.capability.local for item in candidates):
        try:
            capacity = measure_local_capacity_snapshot()
        except Exception:  # noqa: BLE001 - unavailable probes must fail closed
            capacity = LocalCapacitySnapshot(available=False)
    else:
        capacity = LocalCapacitySnapshot(available=False)

    policy = HybridRoutingPolicy(
        remote_processing_approved=payload.remote_processing_approved,
        remote_spend_approved=payload.remote_spend_approved,
        max_remote_cost_usd=payload.max_remote_cost_usd,
    )
    decision = choose_hybrid_route(candidates, request, capacity, policy)
    return {
        "decision": decision.model_dump(mode="json"),
        "providers_considered": len(candidates),
        "execution": "not_started",
        "provider_submission_started": False,
        "generation_approval_required": True,
    }
