"""Security and serialization tests for the bounded multimodal provider contract."""

import base64
import json

import httpx
import pytest
from pydantic import ValidationError

from mrhub.providers.base import ImageInput, ProviderConfigurationError, ProviderRequest
from mrhub.providers.ollama import OllamaProvider
from mrhub.providers.openrouter import OpenRouterProvider


def png_payload() -> str:
    return base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"minimal-test-data").decode("ascii")


def test_image_input_requires_matching_mime_and_magic_bytes():
    image = ImageInput(mime_type="image/png", data_base64=png_payload())
    assert image.mime_type == "image/png"
    with pytest.raises(ValidationError):
        ImageInput(mime_type="image/jpeg", data_base64=png_payload())


def test_image_input_rejects_invalid_base64_and_unsupported_mime():
    with pytest.raises(ValidationError):
        ImageInput(mime_type="image/png", data_base64="not valid base64!!!!")
    with pytest.raises(ValidationError):
        ImageInput(mime_type="image/svg+xml", data_base64=png_payload())


def test_provider_request_bounds_image_count_and_combined_payload():
    image = ImageInput(mime_type="image/png", data_base64=png_payload())
    with pytest.raises(ValidationError):
        ProviderRequest(input_text="inspect", images=(image, image, image, image, image))


def test_ollama_vision_is_opt_in_and_sends_inline_image():
    image = ImageInput(mime_type="image/png", data_base64=png_payload())
    request = ProviderRequest(input_text="Describe this frame", images=(image,))
    calls = []

    def handler(request):
        calls.append(json.loads(request.content))
        return httpx.Response(200, json={"response": "A test frame", "done": True})

    disabled = OllamaProvider("llava", transport=httpx.MockTransport(handler))
    with pytest.raises(ProviderConfigurationError):
        disabled.generate(request)
    assert calls == []

    enabled = OllamaProvider(
        "llava",
        transport=httpx.MockTransport(handler),
        vision_enabled=True,
    )
    result = enabled.generate(request)
    assert result.output_text == "A test frame"
    assert enabled.descriptor.capability.vision is True
    assert calls[0]["images"] == [image.data_base64]


def test_openrouter_vision_is_opt_in_and_uses_data_uri():
    image = ImageInput(mime_type="image/png", data_base64=png_payload())
    request = ProviderRequest(input_text="Describe this frame", images=(image,))
    calls = []

    def handler(request):
        calls.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "A test frame"}, "finish_reason": "stop"}],
                "usage": {},
            },
        )

    disabled = OpenRouterProvider(
        model="vision-model",
        api_key="test-key",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(ProviderConfigurationError):
        disabled.generate(request)
    assert calls == []

    enabled = OpenRouterProvider(
        model="vision-model",
        api_key="test-key",
        transport=httpx.MockTransport(handler),
        vision_enabled=True,
    )
    result = enabled.generate(request)
    assert result.output_text == "A test frame"
    content = calls[0]["messages"][0]["content"]
    assert content[0] == {"type": "text", "text": "Describe this frame"}
    assert content[1]["image_url"]["url"].startswith("data:image/png;base64,")
