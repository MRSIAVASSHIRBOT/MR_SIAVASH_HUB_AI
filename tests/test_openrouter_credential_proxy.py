"""Tests for the loopback-only OpenRouter credential broker."""

from __future__ import annotations

import http.client
import importlib.util
import json
import threading
from pathlib import Path
from typing import ClassVar

BROKER_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "ci"
    / "openrouter_credential_proxy.py"
)
BROKER_SPEC = importlib.util.spec_from_file_location("openrouter_credential_proxy", BROKER_PATH)
assert BROKER_SPEC is not None and BROKER_SPEC.loader is not None
proxy = importlib.util.module_from_spec(BROKER_SPEC)
BROKER_SPEC.loader.exec_module(proxy)


class FakeResponse:
    def __init__(self, status=200, body=b'{"data":[]}'):
        self.status = status
        self._body = body
        self._read = False
        self.headers = {
            "Content-Type": "application/json",
            "Content-Length": str(len(body)),
            "Location": "https://attacker.invalid/redirect",
            "X-Request-Id": "req_123",
        }

    def getheader(self, name):
        return self.headers.get(name)

    def read(self, _amount):
        if self._read:
            return b""
        self._read = True
        return self._body


class FakeConnection:
    instances: ClassVar[list[FakeConnection]] = []
    response_status = 200

    def __init__(self, host, *, timeout, context):
        self.host = host
        self.timeout = timeout
        self.context = context
        self.request_args = None
        self.closed = False
        self.instances.append(self)

    def request(self, method, path, *, body, headers):
        self.request_args = (method, path, body, headers)

    def getresponse(self):
        return FakeResponse(status=self.response_status)

    def close(self):
        self.closed = True


def _request(server, method, path, *, headers=None, body=None):
    client = http.client.HTTPConnection(
        server.server_address[0], server.server_address[1], timeout=3
    )
    client.request(method, path, body=body, headers=headers or {})
    response = client.getresponse()
    payload = response.read()
    client.close()
    return response.status, response.headers, payload


def _start_server(*, response_status=200):
    FakeConnection.instances = []
    FakeConnection.response_status = response_status
    server = proxy.create_server(
        "upstream-secret-value",
        port=0,
        connection_factory=FakeConnection,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def _stop_server(server, thread):
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)


def test_broker_binds_only_to_loopback_and_rejects_requests_without_local_token():
    server, thread = _start_server()
    try:
        assert server.server_address[0] == "127.0.0.1"
        status, _headers, payload = _request(server, "GET", "/api/v1/models")
        assert status == 401
        assert json.loads(payload)["error"]["code"] == "broker_auth_required"
        assert FakeConnection.instances == []
    finally:
        _stop_server(server, thread)


def test_broker_forwards_only_allowlisted_requests_with_its_own_upstream_credential():
    server, thread = _start_server()
    try:
        status, headers, payload = _request(
            server,
            "POST",
            "/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {proxy.BROKER_TOKEN}",
                "Content-Type": "application/json",
                "Accept": "text/event-stream",
                "X-OpenRouter-Api-Key": "caller-controlled-secret",
            },
            body=json.dumps({"model": "cohere/north-mini-code:free", "stream": True}),
        )
        assert status == 200
        assert headers.get("Content-Type") == "application/json"
        assert b'"data":[]' in payload
        assert len(FakeConnection.instances) == 1
        connection = FakeConnection.instances[0]
        assert connection.host == "openrouter.ai"
        method, path, body, upstream_headers = connection.request_args
        assert (method, path) == ("POST", "/api/v1/chat/completions")
        assert json.loads(body)["stream"] is True
        assert upstream_headers["Authorization"] == "Bearer upstream-secret-value"
        assert upstream_headers["Accept"] == "text/event-stream"
        assert "X-OpenRouter-Api-Key" not in upstream_headers
        assert "caller-controlled-secret" not in repr(upstream_headers)
        assert connection.closed is True
    finally:
        _stop_server(server, thread)


def test_broker_rejects_unlisted_paths_and_redirects():
    server, thread = _start_server()
    try:
        status, _headers, payload = _request(
            server,
            "GET",
            "/api/v1/models?url=https://attacker.invalid",
            headers={"Authorization": f"Bearer {proxy.BROKER_TOKEN}"},
        )
        assert status == 404
        assert json.loads(payload)["error"]["code"] == "route_not_found"
        assert FakeConnection.instances == []
    finally:
        _stop_server(server, thread)

    server, thread = _start_server(response_status=302)
    try:
        status, headers, payload = _request(
            server,
            "GET",
            "/api/v1/models",
            headers={"Authorization": f"Bearer {proxy.BROKER_TOKEN}"},
        )
        assert status == 502
        assert headers.get("Location") is None
        assert json.loads(payload)["error"]["code"] == "upstream_redirect_rejected"
    finally:
        _stop_server(server, thread)


def test_request_validation_bounds_payloads_and_methods():
    token = f"Bearer {proxy.BROKER_TOKEN}"
    assert proxy.validate_request("GET", "/api/v1/models", token, None, None) == (200, None)
    assert proxy.validate_request("DELETE", "/api/v1/models", token, None, None)[0] == 405
    assert proxy.validate_request("GET", "/api/v1/models/../keys", token, None, None)[0] == 404
    assert proxy.validate_request(
        "POST", "/api/v1/chat/completions", token, "1", "text/plain"
    )[0] == 415
    assert proxy.validate_request(
        "POST", "/api/v1/chat/completions", token, None, "application/json"
    )[0] == 411
    assert proxy.validate_request(
        "POST",
        "/api/v1/chat/completions",
        token,
        str(proxy.MAX_REQUEST_BYTES + 1),
        "application/json",
    )[0] == 413


def test_broker_rejects_non_object_json_before_upstream_request():
    server, thread = _start_server()
    try:
        status, _headers, payload = _request(
            server,
            "POST",
            "/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {proxy.BROKER_TOKEN}",
                "Content-Type": "application/json",
            },
            body="[]",
        )
        assert status == 400
        assert json.loads(payload)["error"]["code"] == "invalid_json_request"
        assert FakeConnection.instances == []
    finally:
        _stop_server(server, thread)



def test_broker_rejects_unapproved_models_before_forwarding():
    server, thread = _start_server()
    try:
        status, _headers, payload = _request(
            server,
            "POST",
            "/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {proxy.BROKER_TOKEN}",
                "Content-Type": "application/json",
            },
            body=json.dumps({"model": "openai/paid-model", "messages": []}),
        )
        assert status == 403
        assert json.loads(payload)["error"]["code"] == "model_not_allowed"
        assert FakeConnection.instances == []
    finally:
        _stop_server(server, thread)
