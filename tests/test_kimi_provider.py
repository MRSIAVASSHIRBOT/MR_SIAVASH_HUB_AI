import json

import httpx
import pytest

from mrhub.providers.base import (
    ProviderConfigurationError,
    ProviderRequest,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from mrhub.providers.kimi import MAX_KIMI_RESPONSE_BYTES, KimiProvider


def test_kimi_sends_official_bounded_request_and_parses_usage() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert request.url.host == "api.moonshot.ai"
        assert request.url.path == "/v1/chat/completions"
        assert request.headers["Authorization"] == "Bearer test-key"
        assert body["model"] == "kimi-k3.1-pro"
        assert body["max_completion_tokens"] == 128
        assert body["reasoning_effort"] == "high"
        assert body["stream"] is False
        assert body["messages"] == [{"role": "user", "content": "hello"}]
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": "Kimi response"}, "finish_reason": "stop"}
                ],
                "usage": {"prompt_tokens": 12, "completion_tokens": 9},
            },
        )

    provider = KimiProvider(
        model="kimi-k3.1-pro",
        api_key="test-key",
        transport=httpx.MockTransport(handler),
    )
    result = provider.generate(ProviderRequest(input_text="hello", max_output_tokens=128))
    assert result.provider == "moonshot"
    assert result.model == "kimi-k3.1-pro"
    assert result.output_text == "Kimi response"
    assert result.input_tokens == 12
    assert result.output_tokens == 9


def test_kimi_rejects_invalid_configuration() -> None:
    with pytest.raises(ProviderConfigurationError):
        KimiProvider(model="kimi-k3.1-pro", api_key=" ")
    with pytest.raises(ProviderConfigurationError):
        KimiProvider(model="kimi-k3.1-pro", api_key="test", reasoning_effort="extreme")
    with pytest.raises(ProviderConfigurationError):
        KimiProvider(
            model="kimi-k3.1-pro",
            api_key="test",
            timeout_seconds=121,
        )
    with pytest.raises(ProviderConfigurationError):
        KimiProvider(
            model="kimi-k3.1-pro",
            api_key="test",
            timeout_seconds=True,
        )


def test_kimi_timeout_is_sanitized() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("sensitive network detail")

    provider = KimiProvider(
        model="kimi-k3.1-pro",
        api_key="test-key",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(ProviderTimeoutError) as error:
        provider.generate(ProviderRequest(input_text="hello"))
    assert str(error.value) == "Kimi request timed out"
    assert "sensitive" not in str(error.value)
    assert error.value.__cause__ is None
    assert error.value.__context__ is None


def test_kimi_failure_does_not_expose_body_or_follow_redirects() -> None:
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            302,
            headers={"Location": "https://attacker.invalid/collect"},
            text="secret provider details",
        )

    provider = KimiProvider(
        model="kimi-k3.1-pro",
        api_key="test-key",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(ProviderUnavailableError) as error:
        provider.generate(ProviderRequest(input_text="hello"))
    assert str(error.value) == "Kimi service returned an unavailable status"
    assert len(requests) == 1
    assert requests[0].url.host == "api.moonshot.ai"


def test_kimi_health_probe_rejects_boolean_timeout() -> None:
    provider = KimiProvider(model="kimi-k3.1-pro", api_key="test-key")
    with pytest.raises(ProviderConfigurationError):
        provider.health(timeout_seconds=True)


def test_kimi_health_probe_only_checks_model_catalog() -> None:
    paths = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        return httpx.Response(200, json={"data": []})

    provider = KimiProvider(
        model="kimi-k3.1-pro",
        api_key="test-key",
        transport=httpx.MockTransport(handler),
    )
    assert provider.health().available is True
    assert paths == ["/v1/models"]



def test_kimi_vision_sends_validated_inline_image() -> None:
    import base64

    image = b"\x89PNG\r\n\x1a\n" + b"test-image"
    image_data_url = "data:image/png;base64," + base64.b64encode(image).decode()

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        content = body["messages"][0]["content"]
        assert request.url.host == "api.moonshot.ai"
        assert content[0] == {"type": "text", "text": "Describe this image"}
        assert content[1]["type"] == "image_url"
        assert content[1]["image_url"]["url"] == image_data_url
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "A test image"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 20, "completion_tokens": 5},
            },
        )

    provider = KimiProvider(
        model="kimi-k3.1-pro",
        api_key="test-key",
        transport=httpx.MockTransport(handler),
    )
    result = provider.generate_vision(
        prompt="Describe this image",
        image_data_url=image_data_url,
        max_output_tokens=64,
    )
    assert result.output_text == "A test image"
    assert result.input_tokens == 20


@pytest.mark.parametrize(
    "image_data_url",
    [
        "https://example.com/image.png",
        "data:image/svg+xml;base64,PHN2Zy8+",
        "data:image/png;base64,not-valid-base64!",
        "data:image/jpeg;base64," + "iVBORw0KGgo=",
    ],
)
def test_kimi_vision_rejects_unsafe_or_malformed_image_inputs(image_data_url: str) -> None:
    provider = KimiProvider(model="kimi-k3.1-pro", api_key="test-key")
    with pytest.raises(ProviderConfigurationError):
        provider.generate_vision(prompt="Describe this image", image_data_url=image_data_url)


@pytest.mark.parametrize("vision", [False, True])
def test_kimi_rejects_oversized_streamed_provider_responses(vision: bool) -> None:
    import base64

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"x" * (MAX_KIMI_RESPONSE_BYTES + 1))

    provider = KimiProvider(
        model="kimi-k3.1-pro",
        api_key="test-key",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(ProviderUnavailableError, match="exceeded the size limit"):
        if vision:
            image = b"\x89PNG\r\n\x1a\n" + b"test-image"
            image_data_url = "data:image/png;base64," + base64.b64encode(image).decode()
            provider.generate_vision(
                prompt="Describe this image",
                image_data_url=image_data_url,
            )
        else:
            provider.generate(ProviderRequest(input_text="hello"))



def test_kimi_health_probe_rejects_oversized_response() -> None:
    from mrhub.providers.kimi import MAX_KIMI_HEALTH_RESPONSE_BYTES

    provider = KimiProvider(
        model="kimi-k3.1-pro",
        api_key="test-key",
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(
                200,
                content=b"x" * (MAX_KIMI_HEALTH_RESPONSE_BYTES + 1),
            )
        ),
    )

    health = provider.health()

    assert health.available is False
    assert health.reason_code == "provider_unavailable"


@pytest.mark.parametrize("output", ["", "   \n"])
@pytest.mark.parametrize("vision", [False, True])
def test_kimi_rejects_empty_model_output(output: str, vision: bool) -> None:
    import base64

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": output}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 0},
            },
        )

    provider = KimiProvider(
        model="kimi-k3.1-pro",
        api_key="test-key",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(ProviderUnavailableError, match="invalid response"):
        if vision:
            image = b"\x89PNG\r\n\x1a\n" + b"test-image"
            image_data_url = "data:image/png;base64," + base64.b64encode(image).decode()
            provider.generate_vision(
                prompt="Describe this image",
                image_data_url=image_data_url,
            )
        else:
            provider.generate(ProviderRequest(input_text="hello"))


def test_kimi_vision_rejects_boolean_output_token_limit() -> None:
    import base64

    image = b"\x89PNG\r\n\x1a\n" + b"test-image"
    image_data_url = "data:image/png;base64," + base64.b64encode(image).decode()
    provider = KimiProvider(model="kimi-k3.1-pro", api_key="test-key")

    with pytest.raises(ProviderConfigurationError, match="output token limit"):
        provider.generate_vision(
            prompt="Describe this image",
            image_data_url=image_data_url,
            max_output_tokens=True,
        )



def test_kimi_transport_error_does_not_retain_api_key_context() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("private transport details", request=request)

    provider = KimiProvider(
        model="kimi-k3.1-pro",
        api_key="test-key",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(ProviderUnavailableError) as error:
        provider.generate(ProviderRequest(input_text="hello"))
    assert str(error.value) == "Kimi service is unavailable"
    assert error.value.__cause__ is None
    assert error.value.__context__ is None
