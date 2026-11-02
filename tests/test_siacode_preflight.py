import httpx
import pytest

from mrhub.config import Settings
from mrhub.providers.siacode_preflight import SiaCodePreflight


def settings(**overrides):
    values = {
        "siacode_enabled": True,
        "siacode_base_url": "http://127.0.0.1:8765",
        "siacode_timeout_seconds": 0.5,
        "siacode_max_response_bytes": 512,
    }
    values.update(overrides)
    return Settings(**values)


def client_for(handler):
    return httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)


def test_disabled_by_default_does_not_contact_endpoint():
    result = SiaCodePreflight(Settings()).check()
    assert result == {"state": "disabled", "ready": False, "reason_code": "disabled"}


@pytest.mark.parametrize(
    "url",
    [
        None,
        "https://example.com",
        "http://192.168.1.5:8765",
        "http://localhost.evil.example:8765",
        "http://user:password@127.0.0.1:8765",
        "http://127.0.0.1:8765?token=secret",
        "http://127.0.0.1:8765/#fragment",
    ],
)
def test_invalid_or_non_loopback_config_fails_closed(url):
    result = SiaCodePreflight(settings(siacode_base_url=url)).check()
    assert result["state"] == "unconfigured"
    assert result["ready"] is False


def test_healthy_endpoint_returns_only_sanitized_state():
    client = client_for(
        lambda request: httpx.Response(200, json={"status": "ok", "detail": "private"})
    )
    result = SiaCodePreflight(settings(), client=client).check()
    assert result == {"state": "ready", "ready": True, "reason_code": "health_ok"}


def test_redirect_is_rejected_without_following():
    calls = []
    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(302, headers={"Location": "http://127.0.0.1:9999/elsewhere"})
    result = SiaCodePreflight(settings(), client=client_for(handler)).check()
    assert result["reason_code"] == "redirect_rejected"
    assert len(calls) == 1


def test_oversized_health_body_is_rejected():
    client = client_for(lambda request: httpx.Response(200, content=b"x" * 513))
    result = SiaCodePreflight(settings(), client=client).check()
    assert result["reason_code"] == "response_too_large"
    assert result["ready"] is False


def test_invalid_json_is_rejected_without_exposing_body():
    secret_like_body = b'{"token":"never-return-this"}'
    client = client_for(lambda request: httpx.Response(200, content=secret_like_body))
    result = SiaCodePreflight(settings(), client=client).check()
    assert result["reason_code"] == "invalid_health_payload"
    assert "never-return-this" not in str(result)


def test_unreachable_endpoint_returns_stable_error_without_url():
    def handler(request):
        raise httpx.ConnectError("sensitive host and credential should not leak")
    result = SiaCodePreflight(settings(), client=client_for(handler)).check()
    assert result == {
        "state": "unavailable",
        "ready": False,
        "reason_code": "endpoint_unreachable",
    }
