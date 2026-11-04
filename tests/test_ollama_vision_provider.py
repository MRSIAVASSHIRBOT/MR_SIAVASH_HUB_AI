import base64
import json

import httpx
import pytest

from mrhub.providers.base import (
    ProviderConfigurationError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from mrhub.providers.vision import (
    MAX_VISION_IMAGE_BYTES,
    OllamaVisionProvider,
    VisionImage,
    VisionRequest,
)


def _request() -> VisionRequest:
    return VisionRequest(
        prompt="Describe only observable visual details.",
        images=(
            VisionImage(timestamp_seconds=0.0, jpeg_bytes=b"jpeg-frame-0"),
            VisionImage(timestamp_seconds=1.5, jpeg_bytes=b"jpeg-frame-1"),
        ),
        max_output_tokens=256,
    )


def test_ollama_vision_uses_local_images_and_bounded_generation():
    def handler(request):
        body = json.loads(request.content)
        assert request.url.path == "/api/generate"
        assert body["stream"] is False
        assert body["options"]["num_predict"] == 256
        assert body["images"] == [
            base64.b64encode(b"jpeg-frame-0").decode("ascii"),
            base64.b64encode(b"jpeg-frame-1").decode("ascii"),
        ]
        assert "127.0.0.1" in str(request.url)
        return httpx.Response(200, json={"response": '{"style_summary":"cinematic"}'})

    provider = OllamaVisionProvider(
        "llava-local", transport=httpx.MockTransport(handler)
    )
    result = provider.generate(_request())

    assert result.provider == "ollama"
    assert result.model == "llava-local"
    assert result.output_text == '{"style_summary":"cinematic"}'
    assert provider.descriptor.capability.vision is True
    assert provider.descriptor.local is True


def test_ollama_vision_rejects_non_loopback_urls():
    for url in (
        "https://127.0.0.1:11434",
        "http://example.com:11434",
        "http://127.0.0.1:11434/path",
        "http://user:pass@127.0.0.1:11434",
        "http://127.0.0.1:11434?x=1",
    ):
        with pytest.raises(ProviderConfigurationError):
            OllamaVisionProvider("llava-local", base_url=url)


def test_vision_request_enforces_image_count_and_aggregate_bytes():
    with pytest.raises(ValueError):
        VisionImage(timestamp_seconds=-0.1, jpeg_bytes=b"jpeg")
    with pytest.raises(ValueError):
        VisionImage(timestamp_seconds=0, jpeg_bytes=b"x" * (MAX_VISION_IMAGE_BYTES + 1))
    with pytest.raises(TypeError, match="immutable tuple"):
        VisionRequest(
            prompt="x",
            images=[VisionImage(timestamp_seconds=0, jpeg_bytes=b"jpeg")],
        )
    with pytest.raises(TypeError, match="invalid image entry"):
        VisionRequest(prompt="x", images=(object(),))
    with pytest.raises(ValueError):
        VisionRequest(prompt="x", images=())
    with pytest.raises(ValueError):
        VisionRequest(
            prompt="x",
            images=(
                VisionImage(timestamp_seconds=1, jpeg_bytes=b"one"),
                VisionImage(timestamp_seconds=0, jpeg_bytes=b"two"),
            ),
        )
    with pytest.raises(ValueError):
        VisionRequest(
            prompt="x" * 8001,
            images=(VisionImage(timestamp_seconds=0, jpeg_bytes=b"jpeg"),),
        )

    with pytest.raises(ValueError):
        VisionRequest(
            prompt="x",
            images=tuple(
                VisionImage(timestamp_seconds=index, jpeg_bytes=b"x" * 1_400_000)
                for index in range(9)
            ),
        )


def test_ollama_vision_maps_timeout_to_sanitized_error():
    def handler(_request):
        raise httpx.ReadTimeout("private internal detail")

    provider = OllamaVisionProvider(
        "llava-local", transport=httpx.MockTransport(handler)
    )
    with pytest.raises(ProviderTimeoutError) as error:
        provider.generate(_request())
    assert str(error.value) == "Local vision request timed out"


def test_ollama_vision_rejects_invalid_output_shape():
    provider = OllamaVisionProvider(
        "llava-local",
        transport=httpx.MockTransport(lambda _request: httpx.Response(200, json={})),
    )
    with pytest.raises(ProviderUnavailableError):
        provider.generate(_request())


def test_ollama_vision_health_timeout_is_bounded():
    provider = OllamaVisionProvider("llava-local")
    with pytest.raises(ProviderConfigurationError):
        provider.health(timeout_seconds=0.01)
    with pytest.raises(ProviderConfigurationError):
        provider.health(timeout_seconds=11)
