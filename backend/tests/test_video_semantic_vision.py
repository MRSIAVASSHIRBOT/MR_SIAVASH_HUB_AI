import json
from types import SimpleNamespace

import pytest

from mrhub.providers.base import ProviderHealth, ProviderResponse
from mrhub.providers.types import ModelCapability, ModelDescriptor
from mrhub.video_intelligence.frames import ExtractedVideoFrame
from mrhub.video_intelligence import vision


class FakeVisionProvider:
    descriptor = ModelDescriptor(
        provider="ollama",
        model="test-vision",
        capability=ModelCapability(text=True, vision=True),
        local=True,
    )

    def __init__(self, outputs=None):
        self.outputs = list(outputs or [])
        self.requests = []

    def health(self, timeout_seconds=2.0):
        return ProviderHealth(available=True, reason_code="ready")

    def generate(self, request):
        self.requests.append(request)
        output = self.outputs.pop(0) if self.outputs else json.dumps({
            "visual_summary": "A clean product scene",
            "visual_style": ["minimal", "high contrast"],
            "composition": "Centered subject",
            "camera_motion": "Static camera",
            "editing_rhythm": "Slow reveal",
            "text_overlays": [],
        })
        return ProviderResponse(
            provider="ollama",
            model="test-vision",
            output_text=output,
        )


def frames(count):
    return [
        ExtractedVideoFrame(timestamp_seconds=float(index), jpeg_bytes=b"\\xff\\xd8\\xfffixture")
        for index in range(count)
    ]


def test_remote_vision_requires_explicit_per_request_consent():
    settings = SimpleNamespace(
        local_inference_enabled=False,
        local_inference_model=None,
        local_inference_vision_enabled=False,
        remote_inference_enabled=True,
        remote_inference_api_key=SimpleNamespace(get_secret_value=lambda: "secret"),
        remote_inference_model="remote-vision",
        remote_inference_vision_enabled=True,
        remote_inference_base_url="https://openrouter.ai/api/v1",
        remote_inference_timeout_seconds=30.0,
    )
    provider, scope = vision._build_provider(settings, allow_remote=False)
    assert provider is None
    assert scope == "remote_consent_required"

    provider, scope = vision._build_provider(settings, allow_remote=True)
    assert provider is not None
    assert scope == "remote"


def test_local_vision_is_preferred_even_when_remote_consent_exists(monkeypatch):
    settings = SimpleNamespace(
        local_inference_enabled=True,
        local_inference_model="local-vision",
        local_inference_vision_enabled=True,
        local_inference_base_url="http://127.0.0.1:11434",
        local_inference_timeout_seconds=30.0,
        remote_inference_enabled=True,
        remote_inference_api_key=SimpleNamespace(get_secret_value=lambda: "secret"),
        remote_inference_model="remote-vision",
        remote_inference_vision_enabled=True,
        remote_inference_base_url="https://openrouter.ai/api/v1",
        remote_inference_timeout_seconds=30.0,
    )
    provider, scope = vision._build_provider(settings, allow_remote=True)
    assert provider.descriptor.model == "local-vision"
    assert scope == "local"


def test_semantic_analysis_batches_at_most_four_frames_and_returns_structured_facts(monkeypatch):
    provider = FakeVisionProvider()
    monkeypatch.setattr(vision, "_build_provider", lambda *_args, **_kwargs: (provider, "local"))
    result = vision.analyze_video_frames(frames(5), settings=object())

    assert result["status"] == "completed"
    assert result["batch_count"] == 2
    assert len(provider.requests) == 2
    assert [len(item.images) for item in provider.requests] == [4, 1]
    assert result["batches"][0]["analysis"]["visual_summary"] == "A clean product scene"


def test_semantic_analysis_stops_between_batches_when_cancelled(monkeypatch):
    provider = FakeVisionProvider()
    monkeypatch.setattr(vision, "_build_provider", lambda *_args, **_kwargs: (provider, "local"))
    calls = {"count": 0}

    def should_cancel():
        calls["count"] += 1
        return calls["count"] > 1

    result = vision.analyze_video_frames(
        frames(8), settings=object(), should_cancel=should_cancel
    )
    assert result["status"] == "cancelled"
    assert len(provider.requests) == 1


def test_semantic_analysis_rejects_unstructured_or_oversized_model_output(monkeypatch):
    provider = FakeVisionProvider(outputs=['{"visual_summary": "ok", "unexpected": "field"}'])
    monkeypatch.setattr(vision, "_build_provider", lambda *_args, **_kwargs: (provider, "local"))
    result = vision.analyze_video_frames(frames(1), settings=object())
    assert result["status"] == "not_performed"
    assert result["reason_code"] == "vision_provider_or_response_error"


def test_semantic_analysis_does_not_fallback_when_local_provider_is_unhealthy(monkeypatch):
    class UnhealthyProvider(FakeVisionProvider):
        def health(self, timeout_seconds=2.0):
            return ProviderHealth(available=False, reason_code="provider_unavailable")

    provider = UnhealthyProvider()
    monkeypatch.setattr(vision, "_build_provider", lambda *_args, **_kwargs: (provider, "local"))
    result = vision.analyze_video_frames(frames(1), allow_remote=True, settings=object())
    assert result["status"] == "not_performed"
    assert result["reason_code"] == "provider_unavailable"
