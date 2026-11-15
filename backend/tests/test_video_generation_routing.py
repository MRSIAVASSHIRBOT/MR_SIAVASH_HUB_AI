import pytest
from pydantic import ValidationError

from mrhub.video_intelligence.generation import (
    VideoGenerationCapability,
    VideoGenerationRequest,
)
from mrhub.video_intelligence.generation_routing import (
    GenerationRoute,
    GenerationRouteCandidate,
    GenerationRoutePreviewRequest,
    HybridRoutingPolicy,
    LocalCapacitySnapshot,
    RoutingReason,
    choose_hybrid_route,
    measure_local_capacity_snapshot,
    preview_hybrid_route,
)


def _request(**overrides):
    values = {
        "prompt": "Create an original scene.",
        "aspect_ratio": "9:16",
        "duration_seconds": 10,
        "idempotency_key": "route-test-1",
    }
    values.update(overrides)
    return VideoGenerationRequest(**values)


def _candidate(provider, *, local, memory=0, vram=0, cost=None, max_resolution="720p"):
    return GenerationRouteCandidate(
        capability=VideoGenerationCapability(
            provider=provider,
            model="test-v1",
            local=local,
            supported_aspect_ratios=("9:16", "16:9"),
            max_duration_seconds=30,
            max_resolution=max_resolution,
            required_memory_gb=memory,
            required_vram_gb=vram,
        ),
        required_memory_gb=memory,
        required_vram_gb=vram,
        estimated_cost_usd=cost,
    )


def test_hybrid_prefers_local_when_measured_capacity_is_sufficient():
    local = _candidate("local-renderer", local=True, memory=8)
    hosted = _candidate("hosted-test", local=False, cost=0.25)
    decision = choose_hybrid_route(
        [hosted, local],
        _request(),
        LocalCapacitySnapshot(available=True, available_memory_gb=12),
        HybridRoutingPolicy(),
    )
    assert decision.selected is True
    assert decision.route is GenerationRoute.LOCAL
    assert decision.provider == "local-renderer"
    assert decision.estimated_cost_usd == 0


def test_unknown_local_capacity_never_assumes_hardware_is_sufficient():
    local = _candidate("local-renderer", local=True, memory=4)
    decision = choose_hybrid_route(
        [local],
        _request(),
        LocalCapacitySnapshot(available=True),
        HybridRoutingPolicy(),
    )
    assert decision.selected is False
    assert decision.reason is RoutingReason.LOCAL_CAPACITY_UNKNOWN


def test_hosted_fallback_requires_both_explicit_consents():
    hosted = _candidate("hosted-test", local=False, cost=0.2)
    capacity = LocalCapacitySnapshot(available=False)
    decision = choose_hybrid_route(
        [hosted], _request(), capacity,
        HybridRoutingPolicy(remote_processing_approved=True),
    )
    assert decision.selected is False
    assert decision.reason is RoutingReason.REMOTE_CONSENT_REQUIRED


def test_hosted_fallback_requires_known_cost_and_budget():
    hosted = _candidate("hosted-test", local=False, cost=None)
    decision = choose_hybrid_route(
        [hosted], _request(), LocalCapacitySnapshot(available=False),
        HybridRoutingPolicy(
            remote_processing_approved=True,
            remote_spend_approved=True,
            max_remote_cost_usd=1,
        ),
    )
    assert decision.selected is False
    assert decision.reason is RoutingReason.REMOTE_COST_UNKNOWN


def test_hosted_fallback_is_blocked_above_user_budget():
    hosted = _candidate("hosted-test", local=False, cost=1.25)
    decision = choose_hybrid_route(
        [hosted], _request(), LocalCapacitySnapshot(available=False),
        HybridRoutingPolicy(
            remote_processing_approved=True,
            remote_spend_approved=True,
            max_remote_cost_usd=1,
        ),
    )
    assert decision.selected is False
    assert decision.reason is RoutingReason.REMOTE_BUDGET_EXCEEDED


def test_hosted_fallback_selects_lowest_known_cost_within_budget():
    expensive = _candidate("hosted-b", local=False, cost=0.8)
    cheaper = _candidate("hosted-a", local=False, cost=0.3)
    decision = choose_hybrid_route(
        [expensive, cheaper], _request(),
        LocalCapacitySnapshot(available=False),
        HybridRoutingPolicy(
            remote_processing_approved=True,
            remote_spend_approved=True,
            max_remote_cost_usd=1,
        ),
    )
    assert decision.selected is True
    assert decision.route is GenerationRoute.HOSTED
    assert decision.provider == "hosted-a"
    assert decision.estimated_cost_usd == pytest.approx(0.3)


def test_local_gpu_requirement_is_not_satisfied_by_unknown_or_insufficient_vram():
    local = _candidate("local-gpu", local=True, memory=4, vram=8)
    unknown = choose_hybrid_route(
        [local], _request(),
        LocalCapacitySnapshot(available=True, available_memory_gb=16),
        HybridRoutingPolicy(),
    )
    insufficient = choose_hybrid_route(
        [local], _request(),
        LocalCapacitySnapshot(
            available=True, available_memory_gb=16, available_vram_gb=4
        ),
        HybridRoutingPolicy(),
    )
    assert unknown.reason is RoutingReason.LOCAL_CAPACITY_UNKNOWN
    assert insufficient.reason is RoutingReason.LOCAL_CAPACITY_INSUFFICIENT


def test_incompatible_provider_capabilities_are_not_selected():
    local = _candidate("local-renderer", local=True, memory=1)
    decision = choose_hybrid_route(
        [local], _request(duration_seconds=45),
        LocalCapacitySnapshot(available=True, available_memory_gb=16),
        HybridRoutingPolicy(),
    )
    assert decision.selected is False
    assert decision.reason is RoutingReason.NO_COMPATIBLE_PROVIDER


def test_cost_and_resource_metadata_reject_negative_values():
    with pytest.raises(ValueError):
        _candidate("bad-local", local=True, memory=-1)
    with pytest.raises(ValueError):
        _candidate("bad-hosted", local=False, cost=-0.1)


def test_routing_rejects_non_finite_capacity_cost_and_resource_values():
    import math

    with pytest.raises(ValidationError):
        LocalCapacitySnapshot(available=True, available_memory_gb=math.inf)
    with pytest.raises(ValidationError):
        HybridRoutingPolicy(max_remote_cost_usd=math.nan)
    with pytest.raises(ValueError):
        _candidate("bad-cost", local=False, cost=math.inf)
    with pytest.raises(ValueError):
        _candidate("bad-memory", local=True, memory=math.nan)


def test_local_capacity_snapshot_uses_existing_read_only_hardware_diagnostics(monkeypatch):
    from mrhub.diagnostics import hardware

    monkeypatch.setattr(
        hardware,
        "collect_hardware_report",
        lambda: {"memory": {"available_gib": 6.5}},
    )
    snapshot = measure_local_capacity_snapshot()
    assert snapshot.available is True
    assert snapshot.available_memory_gb == 6.5
    assert snapshot.available_vram_gb is None


def test_local_capacity_snapshot_fails_closed_when_memory_is_unavailable(monkeypatch):
    from mrhub.diagnostics import hardware

    monkeypatch.setattr(
        hardware,
        "collect_hardware_report",
        lambda: {"memory": {"available_gib": None}},
    )
    snapshot = measure_local_capacity_snapshot()
    assert snapshot.available is False
    assert snapshot.available_memory_gb is None



def test_unavailable_local_capacity_is_reported_as_unknown_not_insufficient():
    local = _candidate("local-renderer", local=True, memory=4)
    decision = choose_hybrid_route(
        [local],
        _request(),
        LocalCapacitySnapshot(available=False),
        HybridRoutingPolicy(),
    )

    assert decision.selected is False
    assert decision.reason is RoutingReason.LOCAL_CAPACITY_UNKNOWN


def test_local_candidate_selection_is_stable_independent_of_input_order():
    larger = _candidate("local-z", local=True, memory=8)
    smaller = _candidate("local-a", local=True, memory=4)
    capacity = LocalCapacitySnapshot(available=True, available_memory_gb=12)

    forward = choose_hybrid_route(
        [larger, smaller], _request(), capacity, HybridRoutingPolicy()
    )
    reverse = choose_hybrid_route(
        [smaller, larger], _request(), capacity, HybridRoutingPolicy()
    )

    assert forward.provider == reverse.provider == "local-a"
    assert forward.model == reverse.model == "test-v1"


def test_route_preview_is_read_only_and_uses_trusted_local_capacity(monkeypatch):
    from mrhub.video_intelligence import generation_registry as registry_module
    from mrhub.video_intelligence import generation_routing as routing_module
    from mrhub.video_intelligence.generation_registry import VideoGenerationRegistry

    class LocalAdapter:
        capability = VideoGenerationCapability(
            provider="local-preview",
            model="fixture-v1",
            local=True,
            supported_aspect_ratios=("9:16",),
            max_duration_seconds=30,
            max_resolution="720p",
            required_memory_gb=2,
        )

        def submit(self, request):
            raise AssertionError("Route preview must not submit generation work")

        def get_status(self, provider_job_id):
            raise AssertionError("Route preview must not query provider status")

        def find_by_idempotency_key(self, idempotency_key):
            raise AssertionError("Route preview must not reconcile provider jobs")

        def download_output(self, provider_job_id, sink, *, max_bytes):
            raise AssertionError("Route preview must not download provider output")

        def cancel(self, provider_job_id):
            raise AssertionError("Route preview must not cancel provider jobs")

    registry = VideoGenerationRegistry()
    registry.register(LocalAdapter())
    monkeypatch.setattr(registry_module, "video_generation_registry", registry)
    monkeypatch.setattr(
        routing_module,
        "measure_local_capacity_snapshot",
        lambda: LocalCapacitySnapshot(available=True, available_memory_gb=8),
    )

    result = preview_hybrid_route(GenerationRoutePreviewRequest(
        duration_seconds=10,
        aspect_ratio="9:16",
    ))

    assert result["execution"] == "not_started"
    assert result["provider_submission_started"] is False
    assert result["providers_considered"] == 1
    assert result["decision"]["selected"] is True
    assert result["decision"]["route"] == "local"
    assert result["decision"]["provider"] == "local-preview"


def test_route_preview_requires_explicit_remote_consents_and_known_cost(monkeypatch):
    from mrhub.video_intelligence import generation_registry as registry_module
    from mrhub.video_intelligence import generation_routing as routing_module
    from mrhub.video_intelligence.generation_registry import VideoGenerationRegistry

    class HostedAdapter:
        capability = VideoGenerationCapability(
            provider="hosted-preview",
            model="fixture-v1",
            local=False,
            supported_aspect_ratios=("9:16",),
            max_duration_seconds=30,
            max_resolution="1080p",
        )

        def estimate_cost_usd(self, request):
            assert request.duration_seconds == 10
            return 0.35

        def submit(self, request):
            raise AssertionError("Route preview must not submit generation work")

        def get_status(self, provider_job_id):
            raise AssertionError("Route preview must not query provider status")

        def find_by_idempotency_key(self, idempotency_key):
            raise AssertionError("Route preview must not reconcile provider jobs")

        def download_output(self, provider_job_id, sink, *, max_bytes):
            raise AssertionError("Route preview must not download provider output")

        def cancel(self, provider_job_id):
            raise AssertionError("Route preview must not cancel provider jobs")

    registry = VideoGenerationRegistry()
    registry.register(HostedAdapter())
    monkeypatch.setattr(registry_module, "video_generation_registry", registry)
    monkeypatch.setattr(
        routing_module,
        "measure_local_capacity_snapshot",
        lambda: pytest.fail("Hosted-only preview must not probe local hardware"),
    )

    denied = preview_hybrid_route(GenerationRoutePreviewRequest(
        duration_seconds=10,
        aspect_ratio="9:16",
        remote_processing_approved=True,
        max_remote_cost_usd=1,
    ))
    assert denied["decision"]["reason"] == "remote_consent_required"
    assert denied["provider_submission_started"] is False

    approved = preview_hybrid_route(GenerationRoutePreviewRequest(
        duration_seconds=10,
        aspect_ratio="9:16",
        remote_processing_approved=True,
        remote_spend_approved=True,
        max_remote_cost_usd=0.5,
    ))
    assert approved["decision"]["selected"] is True
    assert approved["decision"]["route"] == "hosted"
    assert approved["decision"]["estimated_cost_usd"] == pytest.approx(0.35)
    assert approved["execution"] == "not_started"


def test_route_preview_rejects_client_supplied_capacity_and_invalid_consent_types():
    with pytest.raises(ValidationError):
        GenerationRoutePreviewRequest(
            duration_seconds=10,
            aspect_ratio="9:16",
            available_memory_gb=128,
        )
    with pytest.raises(ValidationError):
        GenerationRoutePreviewRequest(
            duration_seconds=10,
            aspect_ratio="9:16",
            remote_processing_approved="yes",
        )


def test_route_preview_without_registered_adapters_is_unavailable_and_inert(monkeypatch):
    from mrhub.video_intelligence import generation_registry as registry_module
    from mrhub.video_intelligence.generation_registry import VideoGenerationRegistry

    monkeypatch.setattr(registry_module, "video_generation_registry", VideoGenerationRegistry())
    result = preview_hybrid_route(GenerationRoutePreviewRequest(
        duration_seconds=10,
        aspect_ratio="9:16",
    ))
    assert result["decision"]["selected"] is False
    assert result["decision"]["reason"] == "no_compatible_provider"
    assert result["providers_considered"] == 0
    assert result["provider_submission_started"] is False
