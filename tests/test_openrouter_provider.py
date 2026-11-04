import httpx
import pytest

from mrhub.providers.base import (
    ProviderConfigurationError,
    ProviderRequest,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from mrhub.providers.openrouter import OpenRouterProvider


def test_openrouter_rejects_unapproved_origins_and_invalid_urls() -> None:
    for url in (
        "http://openrouter.ai/api/v1",
        "https://evil.example/api/v1",
        "https://openrouter.ai/api/v1?token=secret",
        "https://user:password@openrouter.ai/api/v1",
        "https://openrouter.ai:8443/api/v1",
    ):
        with pytest.raises(ProviderConfigurationError):
            OpenRouterProvider(model="example/free-model", api_key="test-key", base_url=url)


def test_openrouter_sends_bounded_chat_request_and_parses_usage() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        import json

        body = json.loads(request.content)
        assert request.url.path == "/api/v1/chat/completions"
        assert request.headers["Authorization"] == "Bearer test-key"
        assert body["model"] == "example/free-model"
        assert body["max_tokens"] == 96
        assert body["stream"] is False
        assert body["messages"] == [{"role": "user", "content": "hello"}]
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "remote answer"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 11, "completion_tokens": 7},
            },
        )

    provider = OpenRouterProvider(
        model="example/free-model",
        api_key="test-key",
        transport=httpx.MockTransport(handler),
    )
    result = provider.generate(ProviderRequest(input_text="hello", max_output_tokens=96))
    assert result.output_text == "remote answer"
    assert result.provider == "openrouter"
    assert result.input_tokens == 11
    assert result.output_tokens == 7


def test_openrouter_does_not_follow_redirects_or_expose_response_body() -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url)
        return httpx.Response(
            302,
            headers={"Location": "https://attacker.invalid/collect"},
            text="sensitive provider detail",
        )

    provider = OpenRouterProvider(
        model="example/free-model",
        api_key="test-key",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(ProviderUnavailableError) as error:
        provider.generate(ProviderRequest(input_text="hello"))
    assert str(error.value) == "Remote model service returned an unavailable status"
    assert len(calls) == 1
    assert calls[0].host == "openrouter.ai"


def test_openrouter_timeout_is_sanitized() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("private timeout details")

    provider = OpenRouterProvider(
        model="example/free-model",
        api_key="test-key",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(ProviderTimeoutError) as error:
        provider.generate(ProviderRequest(input_text="hello"))
    assert str(error.value) == "Remote model request timed out"


def test_openrouter_invalid_response_fails_closed() -> None:
    provider = OpenRouterProvider(
        model="example/free-model",
        api_key="test-key",
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"choices": []})),
    )
    with pytest.raises(ProviderUnavailableError):
        provider.generate(ProviderRequest(input_text="hello"))


def test_openrouter_health_probe_does_not_start_inference() -> None:
    paths = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        return httpx.Response(200, json={"data": []})

    provider = OpenRouterProvider(
        model="example/free-model",
        api_key="test-key",
        transport=httpx.MockTransport(handler),
    )
    assert provider.health().available is True
    assert paths == ["/api/v1/models"]
