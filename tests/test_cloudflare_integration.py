import httpx
import pytest
from pydantic import SecretStr

from mrhub.config import Settings
from mrhub.integrations import cloudflare
from mrhub.integrations.cloudflare import (
    CloudflareGatewayClient,
    CloudflareGatewayError,
    build_cloudflare_gateway_client,
)

TOKEN = SecretStr("gateway-test-token-that-is-long-enough-123456")
_ORIGINAL_HTTPX_CLIENT = httpx.Client


def _client(monkeypatch, handler, **kwargs):
    def factory(**client_kwargs):
        return _ORIGINAL_HTTPX_CLIENT(
            transport=httpx.MockTransport(handler),
            **client_kwargs,
        )

    monkeypatch.setattr(cloudflare.httpx, "Client", factory)
    return CloudflareGatewayClient(
        gateway_url="https://gateway.example.workers.dev",
        gateway_token=TOKEN,
        **kwargs,
    )


def _envelope(data):
    return httpx.Response(200, json={"ok": True, "data": data, "request_id": "test-request"})


def test_gateway_settings_are_disabled_by_default(monkeypatch):
    for key in (
        "MRH_CLOUDFLARE_GATEWAY_ENABLED",
        "MRH_CLOUDFLARE_GATEWAY_BASE_URL",
        "MRH_CLOUDFLARE_GATEWAY_TOKEN",
        "MRH_CLOUDFLARE_GATEWAY_TIMEOUT_SECONDS",
        "MRH_CLOUDFLARE_GATEWAY_MAX_RESPONSE_BYTES",
    ):
        monkeypatch.delenv(key, raising=False)
    settings = Settings(_env_file=None)
    assert settings.cloudflare_gateway_enabled is False
    assert settings.cloudflare_gateway_base_url is None
    assert settings.cloudflare_gateway_token is None
    assert build_cloudflare_gateway_client(settings) is None


def test_enabled_gateway_requires_complete_server_side_configuration():
    settings = Settings(
        _env_file=None,
        cloudflare_gateway_enabled=True,
        cloudflare_gateway_base_url=None,
        cloudflare_gateway_token=None,
    )
    with pytest.raises(CloudflareGatewayError, match="gateway_not_configured"):
        build_cloudflare_gateway_client(settings)


def test_gateway_constructor_rejects_unsafe_urls_and_credentials():
    for url in (
        "http://gateway.example.workers.dev",
        "https://127.0.0.1",
        "https://localhost",
        "https://gateway.example.workers.dev/path",
        "https://user:pass@gateway.example.workers.dev",
        "https://gateway.example.workers.dev?token=leak",
        "https://gateway.example.workers.dev ",
        "https://bad_host.example.workers.dev",
    ):
        with pytest.raises(ValueError):
            CloudflareGatewayClient(gateway_url=url, gateway_token=TOKEN)
    with pytest.raises(TypeError, match="SecretStr"):
        CloudflareGatewayClient(
            gateway_url="https://gateway.example.workers.dev",
            gateway_token="plain-text-token",
        )


@pytest.mark.parametrize(
    "token",
    [
        SecretStr("short"),
        SecretStr("x" * 513),
        SecretStr("token with spaces and unsafe controls"),
        SecretStr("tökén" * 8),
    ],
)
def test_gateway_constructor_rejects_weak_or_malformed_tokens(token):
    with pytest.raises(ValueError):
        CloudflareGatewayClient(
            gateway_url="https://gateway.example.workers.dev",
            gateway_token=token,
        )


@pytest.mark.parametrize(
    "overrides",
    [
        {"timeout_seconds": True},
        {"timeout_seconds": 8.1},
        {"max_response_bytes": True},
        {"max_response_bytes": 1_048_577},
    ],
)
def test_gateway_constructor_rejects_unbounded_limits(overrides):
    with pytest.raises(ValueError):
        CloudflareGatewayClient(
            gateway_url="https://gateway.example.workers.dev",
            gateway_token=TOKEN,
            **overrides,
        )


def test_workers_uses_fixed_gateway_route_and_projects_typed_metadata(monkeypatch):
    def handler(request):
        assert request.method == "GET"
        assert str(request.url) == "https://gateway.example.workers.dev/v1/workers"
        assert request.headers["Authorization"] == f"Bearer {TOKEN.get_secret_value()}"
        assert request.headers["Accept"] == "application/json"
        return _envelope([
            {"id": "storefront", "etag": "etag-1"},
            {"id": "../invalid", "etag": "unsafe"},
        ])

    client = _client(monkeypatch, handler)
    workers = client.list_workers()
    assert [worker.id for worker in workers] == ["storefront"]
    assert workers[0].etag == "etag-1"


def test_routes_and_d1_use_fixed_gateway_endpoints(monkeypatch):
    paths = []

    def handler(request):
        paths.append(request.url.path)
        if request.url.path == "/v1/worker-routes":
            return _envelope([{
                "id": "route-1",
                "pattern": "gshop11.ir/api/*",
                "script": "gahop",
                "zone_id": "b" * 32,
            }])
        if request.url.path == "/v1/d1-databases":
            return _envelope([{"uuid": "db-1", "name": "gshop-db"}])
        raise AssertionError("unexpected gateway route")

    client = _client(monkeypatch, handler)
    routes = client.list_worker_routes()
    databases = client.list_d1_databases()
    assert routes[0].script == "gahop"
    assert databases[0].name == "gshop-db"
    assert paths == ["/v1/worker-routes", "/v1/d1-databases"]


def test_worker_settings_accept_only_projected_binding_metadata(monkeypatch):
    def handler(request):
        assert request.url.path == "/v1/workers/storefront/settings"
        return _envelope({
            "compatibility_date": "2026-11-06",
            "usage_model": "standard",
            "bindings": [
                {"name": "DB", "type": "d1"},
                {"name": "PAYMENT_SECRET", "type": "secret_text"},
            ],
        })

    client = _client(monkeypatch, handler)
    result = client.get_worker_settings("storefront")
    assert [binding.name for binding in result.bindings] == ["DB", "PAYMENT_SECRET"]
    assert "PAYMENT_SECRET" in result.model_dump_json()
    assert '"text"' not in result.model_dump_json()


def test_worker_settings_reject_unexpected_binding_values(monkeypatch):
    def handler(_request):
        return _envelope({
            "bindings": [{"name": "TOKEN", "type": "secret_text", "text": "secret-value"}],
        })

    client = _client(monkeypatch, handler)
    with pytest.raises(CloudflareGatewayError, match="gateway_invalid_result"):
        client.get_worker_settings("storefront")


def test_invalid_worker_name_is_rejected_before_network(monkeypatch):
    def handler(_request):
        pytest.fail("network must not be called")

    client = _client(monkeypatch, handler)
    with pytest.raises(CloudflareGatewayError, match="invalid_worker_name"):
        client.get_worker_settings("../storefront")


def test_gateway_redirects_and_non_success_responses_fail_closed(monkeypatch):
    def redirect(_request):
        return httpx.Response(302, headers={"Location": "https://attacker.invalid"})

    client = _client(monkeypatch, redirect)
    with pytest.raises(CloudflareGatewayError, match="gateway_redirect_rejected"):
        client.list_workers()

    def failure(_request):
        return httpx.Response(503, text="private gateway details")

    client = _client(monkeypatch, failure)
    with pytest.raises(CloudflareGatewayError, match="gateway_http_error"):
        client.list_workers()


def test_gateway_rejects_non_json_and_malformed_envelopes(monkeypatch):
    def non_json(_request):
        return httpx.Response(200, text="not json", headers={"content-type": "text/plain"})

    client = _client(monkeypatch, non_json)
    with pytest.raises(CloudflareGatewayError, match="gateway_invalid_content_type"):
        client.list_workers()

    def malformed(_request):
        return httpx.Response(200, json={"success": True, "result": []})

    client = _client(monkeypatch, malformed)
    with pytest.raises(CloudflareGatewayError, match="gateway_invalid_envelope"):
        client.list_workers()


def test_gateway_response_size_is_bounded_by_header_and_stream(monkeypatch):
    def header_oversized(_request):
        return httpx.Response(
            200,
            json={"ok": True, "data": []},
            headers={"content-length": "2000000"},
        )

    client = _client(monkeypatch, header_oversized, max_response_bytes=128)
    with pytest.raises(CloudflareGatewayError, match="gateway_response_too_large"):
        client.list_workers()

    def stream_oversized(_request):
        return httpx.Response(
            200,
            stream=httpx.ByteStream(b"x" * 129),
            headers={"content-type": "application/json"},
        )

    client = _client(monkeypatch, stream_oversized, max_response_bytes=128)
    with pytest.raises(CloudflareGatewayError, match="gateway_response_too_large"):
        client.list_workers()


def test_gateway_timeout_is_sanitized(monkeypatch):
    def timeout(_request):
        raise httpx.ReadTimeout("sensitive upstream detail")

    client = _client(monkeypatch, timeout)
    with pytest.raises(CloudflareGatewayError, match="gateway_timeout") as error:
        client.list_workers()
    assert "sensitive" not in str(error.value)


def test_gateway_item_count_and_schema_are_bounded(monkeypatch):
    def excessive(_request):
        return _envelope([{"id": "worker"}] * 1_001)

    client = _client(monkeypatch, excessive)
    with pytest.raises(CloudflareGatewayError, match="gateway_item_limit"):
        client.list_workers()

    def invalid_schema(_request):
        return _envelope([{"id": "worker", "unexpected": "field"}])

    client = _client(monkeypatch, invalid_schema)
    with pytest.raises(CloudflareGatewayError, match="gateway_invalid_result"):
        client.list_workers()
