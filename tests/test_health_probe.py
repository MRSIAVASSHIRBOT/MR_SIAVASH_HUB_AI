import asyncio

from mrhub.integrations import health_probe


class FakeResponse:
    def __init__(self, status_code=200, chunks=()):
        self.status_code = status_code
        self.is_redirect = 300 <= status_code < 400
        self._chunks = chunks

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def aiter_bytes(self, chunk_size=1024):
        for chunk in self._chunks:
            yield chunk


class FakeClient:
    def __init__(self, response, **kwargs):
        self.response = response
        self.kwargs = kwargs
        self.request_args = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    def stream(self, method, url, **kwargs):
        self.request_args = (method, url, kwargs)
        return self.response


def test_probe_rejects_invalid_targets_without_constructing_client(monkeypatch):
    def unexpected_client(*_args, **_kwargs):
        raise AssertionError("invalid target must be rejected before network client creation")

    monkeypatch.setattr(health_probe.httpx, "AsyncClient", unexpected_client)
    result = asyncio.run(
        health_probe.probe_loopback_service(
            "https://example.com", "/health", timeout_seconds=1, max_response_bytes=1024
        )
    )
    assert result == {"contract_version": "1.0", "status": "invalid_configuration", "configured": False}


def test_probe_disables_redirects_and_environment_proxy_inheritance(monkeypatch):
    response = FakeResponse(status_code=302)
    clients = []

    def fake_client(**kwargs):
        client = FakeClient(response, **kwargs)
        clients.append(client)
        return client

    monkeypatch.setattr(health_probe.httpx, "AsyncClient", fake_client)
    result = asyncio.run(
        health_probe.probe_loopback_service(
            "http://127.0.0.1:18789", "/health", timeout_seconds=1.5, max_response_bytes=1024
        )
    )
    assert result == {"contract_version": "1.0", "status": "rejected_redirect", "configured": True}
    assert clients[0].kwargs["follow_redirects"] is False
    assert clients[0].kwargs["trust_env"] is False
    assert clients[0].request_args[0:2] == ("GET", "http://127.0.0.1:18789/health")


def test_probe_enforces_response_byte_limit(monkeypatch):
    response = FakeResponse(chunks=(b"a" * 700, b"b" * 400))

    def fake_client(**kwargs):
        return FakeClient(response, **kwargs)

    monkeypatch.setattr(health_probe.httpx, "AsyncClient", fake_client)
    result = asyncio.run(
        health_probe.probe_loopback_service(
            "http://127.0.0.1:18789", "/health", timeout_seconds=1, max_response_bytes=1024
        )
    )
    assert result == {"contract_version": "1.0", "status": "response_too_large", "configured": True}


def test_probe_returns_only_sanitized_reachability_metadata(monkeypatch):
    response = FakeResponse(status_code=200, chunks=(b'{"ready":true}',))

    def fake_client(**kwargs):
        return FakeClient(response, **kwargs)

    monkeypatch.setattr(health_probe.httpx, "AsyncClient", fake_client)
    result = asyncio.run(
        health_probe.probe_loopback_service(
            "http://127.0.0.1:18789", "/health", timeout_seconds=1, max_response_bytes=1024
        )
    )
    assert result == {
        "contract_version": "1.0",
        "status": "reachable",
        "configured": True,
        "http_status": 200,
    }
    assert "ready" not in str(result)
