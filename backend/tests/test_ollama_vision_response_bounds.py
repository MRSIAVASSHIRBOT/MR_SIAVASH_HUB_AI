import json

import httpx
import pytest

from mrhub.providers.base import ProviderUnavailableError
from mrhub.providers.vision import (
    MAX_VISION_RESPONSE_BYTES,
    OllamaVisionProvider,
    VisionImage,
    VisionRequest,
)


def _request():
    return VisionRequest(
        prompt="Describe the supplied frame.",
        images=(VisionImage(timestamp_seconds=0.0, jpeg_bytes=b"jpeg-frame"),),
        max_output_tokens=32,
    )


def test_ollama_vision_accepts_bounded_json_response():
    expected = "A bounded visual description."

    def handler(request):
        payload = json.loads(request.content)
        assert payload["model"] == "vision-test"
        assert payload["stream"] is False
        assert len(payload["images"]) == 1
        return httpx.Response(200, json={"response": expected})

    provider = OllamaVisionProvider(
        model="vision-test",
        transport=httpx.MockTransport(handler),
    )

    result = provider.generate(_request())

    assert result.output_text == expected
    assert result.provider == "ollama"


def test_ollama_vision_rejects_response_exceeding_byte_limit():
    oversized = b'{"response":"' + (b"x" * MAX_VISION_RESPONSE_BYTES) + b'"}'

    provider = OllamaVisionProvider(
        model="vision-test",
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(
                200,
                headers={"content-type": "application/json"},
                content=oversized,
            )
        ),
    )

    with pytest.raises(ProviderUnavailableError):
        provider.generate(_request())


def test_ollama_vision_rejects_invalid_json_within_byte_limit():
    provider = OllamaVisionProvider(
        model="vision-test",
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(200, content=b"{not-json")
        ),
    )

    with pytest.raises(ProviderUnavailableError):
        provider.generate(_request())
