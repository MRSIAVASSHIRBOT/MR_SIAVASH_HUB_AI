"""MCP service startup guard tests."""

from types import SimpleNamespace

import pytest

from mrhub import mcp_service


def _settings(**overrides):
    values = {
        "mcp_enabled": True,
        "mcp_host": "127.0.0.1",
        "mcp_port": 8765,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_mcp_service_refuses_to_start_when_disabled(monkeypatch):
    monkeypatch.setattr(
        mcp_service, "get_settings", lambda: _settings(mcp_enabled=False)
    )

    with pytest.raises(SystemExit, match="MCP service is disabled"):
        mcp_service.main()


@pytest.mark.parametrize("host", ["0.0.0.0", "localhost", "hub.local"])
def test_mcp_service_refuses_non_numeric_loopback_bind(host, monkeypatch):
    monkeypatch.setattr(
        mcp_service, "get_settings", lambda: _settings(mcp_host=host)
    )
    monkeypatch.setattr(
        mcp_service,
        "create_mcp_server",
        lambda: pytest.fail("server must not be created for a non-numeric loopback bind"),
    )

    with pytest.raises(SystemExit, match="numeric loopback address"):
        mcp_service.main()


@pytest.mark.parametrize("host", ["127.0.0.1", "::1"])
def test_mcp_service_starts_explicitly_with_bounded_transport(host, monkeypatch):
    calls = {}

    class FakeServer:
        def run(self, **kwargs):
            calls.update(kwargs)

    monkeypatch.setattr(mcp_service, "get_settings", lambda: _settings(mcp_host=host))
    monkeypatch.setattr(mcp_service, "create_mcp_server", FakeServer)

    mcp_service.main()

    assert calls == {
        "transport": "streamable-http",
        "host": host,
        "port": 8765,
        "streamable_http_path": "/mcp",
        "stateless_http": True,
        "max_request_body_size": 1_048_576,
        "max_sessions": 20,
        "session_idle_timeout": 300,
    }
