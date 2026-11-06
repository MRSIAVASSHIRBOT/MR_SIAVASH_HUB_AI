import asyncio
import json

import httpx
import pytest

from mrhub.integrations import cloudflare
from mrhub.integrations.cloudflare import (
    CloudflareAdapterError,
    CloudflareReadOnlyClient,
)

ACCOUNT_ID = "a" * 32
ZONE_ID = "b" * 32


def _client(monkeypatch, handler, **kwargs):
    original_client = httpx.AsyncClient

    def factory(**client_kwargs):
        return original_client(
            transport=httpx.MockTransport(handler),
            **client_kwargs,
        )

    monkeypatch.setattr(cloudflare.httpx, "AsyncClient", factory)
    return CloudflareReadOnlyClient(
        api_token="test-token",
        allowed_account_ids={ACCOUNT_ID},
        allowed_zone_ids={ZONE_ID},
        **kwargs,
    )


def test_constructor_requires_explicit_valid_allowlists():
    with pytest.raises(ValueError):
        CloudflareReadOnlyClient(api_token="token", allowed_account_ids=set())
    with pytest.raises(ValueError):
        CloudflareReadOnlyClient(api_token="token", allowed_account_ids={"not-an-id"})
    with pytest.raises(ValueError):
        CloudflareReadOnlyClient(api_token=" ", allowed_account_ids={ACCOUNT_ID})


@pytest.mark.parametrize(
    "overrides",
    [
        {"timeout_seconds": True},
        {"timeout_seconds": float("nan")},
        {"max_response_bytes": True},
        {"max_response_bytes": 1_048_577},
    ],
)
def test_constructor_rejects_ambiguous_or_unbounded_limits(overrides):
    with pytest.raises(ValueError):
        CloudflareReadOnlyClient(
            api_token="token",
            allowed_account_ids={ACCOUNT_ID},
            **overrides,
        )


@pytest.mark.parametrize("token", ["token\\r\\nInjected: value", "x" * 513, "tökén"])
def test_constructor_rejects_malformed_or_oversized_tokens(token):
    with pytest.raises(ValueError):
        CloudflareReadOnlyClient(
            api_token=token,
            allowed_account_ids={ACCOUNT_ID},
        )


def test_account_and_zone_scope_are_enforced_before_network():
    client = CloudflareReadOnlyClient(
        api_token="token",
        allowed_account_ids={ACCOUNT_ID},
        allowed_zone_ids={ZONE_ID},
    )
    with pytest.raises(CloudflareAdapterError, match="account_not_allowlisted"):
        asyncio.run(client.list_workers("c" * 32))
    with pytest.raises(CloudflareAdapterError, match="zone_not_allowlisted"):
        asyncio.run(client.list_worker_routes("d" * 32))


def test_worker_settings_redact_all_binding_values(monkeypatch):
    secret_value = "must-never-appear-in-output"

    def handler(request):
        assert request.method == "GET"
        assert request.url.path.endswith("/workers/scripts/storefront/settings")
        assert request.headers["Authorization"] == "Bearer test-token"
        return httpx.Response(
            200,
            json={
                "success": True,
                "result": {
                    "compatibility_date": "2026-09-11",
                    "usage_model": "standard",
                    "bindings": [
                        {"name": "DB", "type": "d1", "id": "database-id"},
                        {"name": "PAYMENT_SECRET", "type": "secret_text", "text": secret_value},
                        {"name": "ALLOWED_ORIGINS", "type": "plain_text", "text": secret_value},
                    ],
                },
            },
        )

    client = _client(monkeypatch, handler)
    result = asyncio.run(client.get_worker_settings(ACCOUNT_ID, "storefront"))
    serialized = result.model_dump_json()

    assert [item.name for item in result.bindings] == [
        "DB",
        "PAYMENT_SECRET",
        "ALLOWED_ORIGINS",
    ]
    assert secret_value not in serialized
    assert '"text":' not in serialized
    assert result.compatibility_date == "2026-09-11"


def test_rejects_invalid_worker_names_without_network(monkeypatch):
    def handler(_request):
        pytest.fail("network must not be called for an invalid worker name")

    client = _client(monkeypatch, handler)
    with pytest.raises(CloudflareAdapterError, match="invalid_worker_name"):
        asyncio.run(client.get_worker_settings(ACCOUNT_ID, "../storefront"))


def test_rejects_oversized_provider_response(monkeypatch):
    def handler(_request):
        return httpx.Response(
            200,
            content=json.dumps({"success": True, "result": []}).encode() + b" " * 128,
        )

    client = _client(monkeypatch, handler, max_response_bytes=64)
    with pytest.raises(CloudflareAdapterError, match="provider_response_too_large"):
        asyncio.run(client.list_workers(ACCOUNT_ID))


def test_rejects_provider_redirects(monkeypatch):
    def handler(_request):
        return httpx.Response(302, headers={"Location": "https://example.invalid"})

    client = _client(monkeypatch, handler)
    with pytest.raises(CloudflareAdapterError, match="provider_redirect_rejected"):
        asyncio.run(client.list_workers(ACCOUNT_ID))


def test_lists_workers_using_fixed_cloudflare_endpoint(monkeypatch):
    def handler(request):
        assert request.url.host == "api.cloudflare.com"
        assert request.url.path == f"/client/v4/accounts/{ACCOUNT_ID}/workers/scripts"
        assert request.url.params["page"] == "1"
        return httpx.Response(
            200,
            json={
                "success": True,
                "result": [
                    {"id": "storefront", "etag": "etag-1"},
                    {"id": "../invalid"},
                ],
                "result_info": {"total_pages": 1},
            },
        )

    client = _client(monkeypatch, handler)
    workers = asyncio.run(client.list_workers(ACCOUNT_ID))
    assert [worker.id for worker in workers] == ["storefront"]
