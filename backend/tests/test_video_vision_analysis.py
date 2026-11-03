import json

import pytest

from mrhub.providers.base import ProviderUnavailableError
from mrhub.providers.vision import VisionResponse
from mrhub.video_intelligence.frames import ExtractedVideoFrame
from mrhub.video_intelligence.visual_schemas import VisualAnalysisResult
from mrhub.video_intelligence.vision import analyze_sampled_frames


def _frames():
    return [
        ExtractedVideoFrame(timestamp_seconds=0.0, jpeg_bytes=b"jpeg-0"),
        ExtractedVideoFrame(timestamp_seconds=1.5, jpeg_bytes=b"jpeg-1"),
    ]


def _visual_json(timestamp_a=0.0, timestamp_b=1.5):
    return json.dumps({
        "style_summary": "A restrained cinematic sequence with balanced framing.",
        "observations": [
            {
                "timestamp_seconds": timestamp_a,
                "description": "A wide view with the subject placed near the center.",
                "shot_scale": "wide",
                "camera_movement": "static",
                "composition": "Centered subject with negative space.",
                "lighting": "Soft directional light.",
                "color_notes": ["emerald", "charcoal"],
                "confidence": 0.91,
            },
            {
                "timestamp_seconds": timestamp_b,
                "description": "The framing moves closer while preserving the subject.",
                "shot_scale": "medium",
                "camera_movement": "tracking",
                "composition": "Subject remains near the center.",
                "lighting": "Consistent soft light.",
                "color_notes": ["emerald"],
                "confidence": 0.78,
            },
        ],
    })


def test_local_vision_analysis_uses_actual_timestamps_and_transient_frames():
    captured = {}

    class FakeProvider:
        def __init__(self, **kwargs):
            captured["settings"] = kwargs

        def generate(self, request):
            captured["request"] = request
            return VisionResponse(
                provider="ollama", model="local-vision", output_text=_visual_json()
            )

    result = analyze_sampled_frames(
        _frames(),
        enabled=True,
        model="local-vision",
        base_url="http://127.0.0.1:11434",
        timeout_seconds=30,
        provider_factory=FakeProvider,
    )

    assert result["status"] == "completed"
    assert result["provider"] == "ollama"
    assert result["model"] == "local-vision"
    assert len(result["observations"]) == 2
    request = captured["request"]
    assert [image.timestamp_seconds for image in request.images] == [0.0, 1.5]
    assert [image.jpeg_bytes for image in request.images] == [b"jpeg-0", b"jpeg-1"]
    assert "0: 0.000 seconds" in request.prompt
    assert "2: 1.500 seconds" in request.prompt
    assert captured["settings"]["base_url"] == "http://127.0.0.1:11434"


def test_local_vision_is_opt_in_and_never_constructs_provider_when_disabled():
    def forbidden_factory(**_kwargs):
        pytest.fail("Vision provider must not be constructed while disabled")

    result = analyze_sampled_frames(
        _frames(),
        enabled=False,
        model="local-vision",
        base_url="http://127.0.0.1:11434",
        timeout_seconds=30,
        provider_factory=forbidden_factory,
    )
    assert result == {
        "status": "not_configured",
        "reason_code": "local_vision_disabled",
    }


def test_local_vision_rejects_model_invented_timestamps():
    class FakeProvider:
        def __init__(self, **_kwargs):
            pass

        def generate(self, _request):
            return VisionResponse(
                provider="ollama",
                model="local-vision",
                output_text=_visual_json(0.25, 1.5),
            )

    result = analyze_sampled_frames(
        _frames(),
        enabled=True,
        model="local-vision",
        base_url="http://127.0.0.1:11434",
        timeout_seconds=30,
        provider_factory=FakeProvider,
    )
    assert result == {
        "status": "invalid_response",
        "reason_code": "visual_timestamp_mismatch",
    }


def test_local_vision_returns_sanitized_provider_failure():
    class FakeProvider:
        def __init__(self, **_kwargs):
            pass

        def generate(self, _request):
            raise ProviderUnavailableError("private provider response")

    result = analyze_sampled_frames(
        _frames(),
        enabled=True,
        model="local-vision",
        base_url="http://127.0.0.1:11434",
        timeout_seconds=30,
        provider_factory=FakeProvider,
    )
    assert result == {
        "status": "unavailable",
        "reason_code": "provider_unavailable",
    }


def test_visual_schema_rejects_extra_fields_and_duplicate_timestamps():
    with pytest.raises(ValueError):
        VisualAnalysisResult.model_validate({
            "style_summary": "summary",
            "extra": "not allowed",
            "observations": [],
        })

    duplicated = json.loads(_visual_json())
    duplicated["observations"][1]["timestamp_seconds"] = 0.0
    with pytest.raises(ValueError):
        VisualAnalysisResult.model_validate(duplicated)
