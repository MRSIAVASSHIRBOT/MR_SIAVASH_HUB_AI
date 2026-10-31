import httpx
import pytest

from mrhub.providers.base import (
    ProviderConfigurationError,
    ProviderRequest,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from mrhub.providers.ollama import OllamaProvider


def test_ollama_rejects_non_loopback_urls():
    for url in (
        "https://127.0.0.1:11434",
        "http://example.com:11434",
        "http://127.0.0.1:11434/path",
        "http://user:pass@127.0.0.1:11434",
        "http://127.0.0.1:11434?x=1",
    ):
        with pytest.raises(ProviderConfigurationError):
            OllamaProvider("tiny-model", base_url=url)


def test_ollama_accepts_localhost_and_ipv4_loopback():
    assert OllamaProvider("tiny-model").base_url == "http://127.0.0.1:11434"
    assert OllamaProvider("tiny-model", "http://localhost:1234").base_url == (
        "http://localhost:1234"
    )


def test_ollama_generate_parses_response_and_bounds_generation():
    def handler(request):
        import json

        body = json.loads(request.content)
        assert request.url.path == "/api/generate"
        assert body["stream"] is False
        assert body["options"]["num_predict"] == 128
        return httpx.Response(
            200,
            json={
                "response": "local answer",
                "prompt_eval_count": 12,
                "eval_count": 7,
                "done_reason": "stop",
            },
        )

    provider = OllamaProvider("tiny-model", transport=httpx.MockTransport(handler))
    result = provider.generate(
        ProviderRequest(input_text="hello", max_output_tokens=128)
    )
    assert result.output_text == "local answer"
    assert result.input_tokens == 12
    assert result.output_tokens == 7
    assert result.provider == "ollama"


def test_ollama_health_reports_unavailable_without_leaking_details():
    def handler(request):
        return httpx.Response(503, text="private server detail")

    provider = OllamaProvider("tiny-model", transport=httpx.MockTransport(handler))
    health = provider.health()
    assert health.available is False
    assert health.reason_code == "provider_unavailable"


def test_ollama_maps_timeout_to_sanitized_error():
    def handler(request):
        raise httpx.ReadTimeout("sensitive internal detail")

    provider = OllamaProvider("tiny-model", transport=httpx.MockTransport(handler))
    with pytest.raises(ProviderTimeoutError) as error:
        provider.generate(ProviderRequest(input_text="hello"))
    assert str(error.value) == "Local model request timed out"


def test_ollama_rejects_invalid_response_shape():
    provider = OllamaProvider(
        "tiny-model",
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json={})),
    )
    with pytest.raises(ProviderUnavailableError):
        provider.generate(ProviderRequest(input_text="hello"))
