from io import BytesIO

import pytest
from pydantic import ValidationError

from mrhub.video_intelligence.generation import (
    GenerationStatus,
    VideoGenerationCapability,
    VideoGenerationRequest,
    VideoGenerationResult,
    VideoGenerationSubmission,
)
from mrhub.video_intelligence.generation_registry import VideoGenerationRegistry


def _request(**overrides):
    values = {
        "prompt": "Create an original cinematic scene.",
        "aspect_ratio": "9:16",
        "duration_seconds": 10,
        "idempotency_key": "request-123",
    }
    values.update(overrides)
    return VideoGenerationRequest(**values)


def test_generation_request_is_bounded_and_rejects_unknown_fields():
    assert _request().resolution == "720p"
    with pytest.raises(ValidationError):
        _request(duration_seconds=61)
    with pytest.raises(ValidationError):
        _request(aspect_ratio="2:1")
    with pytest.raises(ValidationError):
        _request(prompt="x" * 20_001)
    with pytest.raises(ValidationError):
        _request(untrusted_remote_url="https://example.invalid")


def test_generation_submission_and_result_are_strict():
    submission = VideoGenerationSubmission(
        provider="local",
        model="renderer-v1",
        provider_job_id="job-1",
        status=GenerationStatus.ACCEPTED,
        progress_percent=0,
    )
    assert submission.status is GenerationStatus.ACCEPTED
    with pytest.raises(ValidationError):
        VideoGenerationResult(
            provider="local",
            model="renderer-v1",
            provider_job_id="job-1",
            status=GenerationStatus.SUCCEEDED,
            output_bytes=100_000_001,
        )
    with pytest.raises(ValidationError):
        VideoGenerationResult(
            provider="local",
            model="renderer-v1",
            provider_job_id="job-2",
            status=GenerationStatus.SUCCEEDED,
        )
    with pytest.raises(ValidationError):
        VideoGenerationResult(
            provider="local",
            model="renderer-v1",
            provider_job_id="job-3",
            status=GenerationStatus.FAILED,
        )
    with pytest.raises(ValidationError):
        VideoGenerationResult(
            provider="local",
            model="renderer-v1",
            provider_job_id="job-4",
            status=GenerationStatus.FAILED,
            error_code="provider failed: private token and signed URL",
        )
    failed = VideoGenerationResult(
        provider="local",
        model="renderer-v1",
        provider_job_id="job-5",
        status=GenerationStatus.FAILED,
        error_code="provider_generation_failed",
    )
    assert failed.error_code == "provider_generation_failed"


def test_generation_registry_is_empty_until_explicit_adapter_registration():
    registry = VideoGenerationRegistry()
    assert registry.catalog() == []
    with pytest.raises(LookupError):
        registry.get("remote", "paid-model")

    class FakeAdapter:
        capability = VideoGenerationCapability(
            provider="test",
            model="fake-v1",
            local=True,
            supported_aspect_ratios=("9:16", "16:9"),
            max_duration_seconds=30,
            max_resolution="720p",
        )

        def submit(self, request):
            return VideoGenerationSubmission(
                provider="test",
                model="fake-v1",
                provider_job_id=request.idempotency_key,
                status=GenerationStatus.ACCEPTED,
                progress_percent=0,
            )

        def get_status(self, provider_job_id):
            return VideoGenerationResult(
                provider="test",
                model="fake-v1",
                provider_job_id=provider_job_id,
                status=GenerationStatus.RUNNING,
            )

        def find_by_idempotency_key(self, idempotency_key):
            if idempotency_key == "request-123":
                return VideoGenerationSubmission(
                    provider="test",
                    model="fake-v1",
                    provider_job_id="provider-job-from-idempotency-key",
                    status=GenerationStatus.ACCEPTED,
                    progress_percent=0,
                )
            return None

        def download_output(self, provider_job_id, sink, *, max_bytes):
            content = b"fake-mp4"
            if len(content) > max_bytes:
                raise ValueError("output_too_large")
            return sink.write(content)

        def cancel(self, provider_job_id):
            return True

    adapter = FakeAdapter()
    registry.register(adapter)
    assert registry.catalog() == [adapter.capability]
    assert registry.get("test", "fake-v1") is adapter
    recovered = adapter.find_by_idempotency_key("request-123")
    assert recovered is not None
    assert recovered.provider_job_id == "provider-job-from-idempotency-key"
    assert adapter.find_by_idempotency_key("not-found") is None
    sink = BytesIO()
    assert adapter.download_output("job-1", sink, max_bytes=100) == 8
    assert sink.getvalue() == b"fake-mp4"
    with pytest.raises(ValueError):
        registry.register(adapter)


def test_generation_capabilities_require_unique_supported_aspect_ratios():
    base = {
        "provider": "test",
        "model": "fixture-v1",
        "local": True,
        "supported_aspect_ratios": ("9:16", "16:9"),
        "max_duration_seconds": 30,
        "max_resolution": "720p",
    }
    assert VideoGenerationCapability(**base).supported_aspect_ratios == ("9:16", "16:9")

    with pytest.raises(ValidationError):
        VideoGenerationCapability(**{**base, "supported_aspect_ratios": ()})
    with pytest.raises(ValidationError):
        VideoGenerationCapability(**{**base, "supported_aspect_ratios": ("2:1",)})
    with pytest.raises(ValidationError):
        VideoGenerationCapability(**{**base, "supported_aspect_ratios": ("9:16", "9:16")})


def test_generation_registry_rejects_adapter_without_reconciliation_lookup():
    class AdapterWithoutLookup:
        capability = VideoGenerationCapability(
            provider="legacy",
            model="legacy-v1",
            local=True,
            supported_aspect_ratios=("16:9",),
            max_duration_seconds=30,
            max_resolution="720p",
        )

    registry = VideoGenerationRegistry()
    with pytest.raises(TypeError, match="find_by_idempotency_key"):
        registry.register(AdapterWithoutLookup())
    assert registry.catalog() == []


def test_authenticated_provider_catalog_fails_closed_when_no_adapter_is_configured():
    from client_helpers import authenticated_client

    client = authenticated_client()
    try:
        response = client.get("/video-intelligence/generation/providers")
        assert response.status_code == 200
        payload = response.json()
        assert payload["providers"] == []
        assert payload["count"] == 0
        assert payload["generation_available"] is False
        assert payload["reason_code"] == "provider_unavailable"
        assert payload["execution"] == "not_started"
    finally:
        client.close()


def test_authenticated_provider_catalog_lists_only_registered_capabilities_without_execution(
    monkeypatch,
):
    from client_helpers import authenticated_client
    from mrhub.video_intelligence import generation_registry as registry_module

    class NonExecutingAdapter:
        capability = VideoGenerationCapability(
            provider="test-local",
            model="fixture-v1",
            local=True,
            supported_aspect_ratios=("9:16", "16:9"),
            max_duration_seconds=24,
            max_resolution="720p",
        )

        def submit(self, request):
            raise AssertionError("Catalog lookup must not submit generation work")

        def get_status(self, provider_job_id):
            raise AssertionError("Catalog lookup must not query provider job status")

        def find_by_idempotency_key(self, idempotency_key):
            raise AssertionError("Catalog lookup must not reconcile provider jobs")

        def download_output(self, provider_job_id, sink, *, max_bytes):
            raise AssertionError("Catalog lookup must not download provider output")

        def cancel(self, provider_job_id):
            raise AssertionError("Catalog lookup must not cancel provider jobs")

    registry = VideoGenerationRegistry()
    adapter = NonExecutingAdapter()
    registry.register(adapter)
    monkeypatch.setattr(registry_module, "video_generation_registry", registry)

    client = authenticated_client()
    try:
        response = client.get("/video-intelligence/generation/providers")
        assert response.status_code == 200
        payload = response.json()
        assert payload == {
            "providers": [adapter.capability.model_dump(mode="json")],
            "count": 1,
            "generation_available": True,
            "reason_code": None,
            "execution": "not_started",
        }
    finally:
        client.close()


def test_generation_registry_rejects_incomplete_provider_contract():
    class IncompleteAdapter:
        capability = VideoGenerationCapability(
            provider="incomplete",
            model="fixture-v1",
            local=True,
            supported_aspect_ratios=("16:9",),
            max_duration_seconds=30,
            max_resolution="720p",
        )

        def find_by_idempotency_key(self, idempotency_key):
            return None

    registry = VideoGenerationRegistry()
    with pytest.raises(TypeError, match="submit"):
        registry.register(IncompleteAdapter())
    assert registry.catalog() == []


def test_generation_registry_rejects_invalid_capability_before_registration():
    class InvalidCapabilityAdapter:
        def __init__(self):
            self.capability = {"provider": "test", "model": "fixture-v1"}

        def submit(self, request):
            raise AssertionError("Invalid adapters must never be called")

        def get_status(self, provider_job_id):
            raise AssertionError("Invalid adapters must never be called")

        def find_by_idempotency_key(self, idempotency_key):
            raise AssertionError("Invalid adapters must never be called")

        def download_output(self, provider_job_id, sink, *, max_bytes):
            raise AssertionError("Invalid adapters must never be called")

        def cancel(self, provider_job_id):
            raise AssertionError("Invalid adapters must never be called")

    registry = VideoGenerationRegistry()
    with pytest.raises(TypeError, match="VideoGenerationCapability"):
        registry.register(InvalidCapabilityAdapter())
    assert registry.catalog() == []
