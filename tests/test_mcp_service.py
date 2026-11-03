"""MCP service startup and configuration guard tests."""

from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from mrhub import mcp_service
from mrhub.config import Settings


def _settings(**overrides):
    values = {
        "mcp_enabled": True,
        "mcp_host": "127.0.0.1",
        "mcp_port": 8765,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_mcp_settings_default_to_disabled_loopback_only():
    settings = Settings(_env_file=None)
    assert settings.mcp_enabled is False
    assert settings.mcp_host == "127.0.0.1"
    assert settings.mcp_port == 8765


@pytest.mark.parametrize("host", ["localhost", "0.0.0.0", "192.0.2.10", "hub.local"])
def test_mcp_settings_reject_non_loopback_host_values(host):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, mcp_host=host)


@pytest.mark.parametrize("host", ["127.0.0.1", "::1"])
def test_mcp_settings_accept_numeric_loopback_values(host):
    settings = Settings(_env_file=None, mcp_host=host)
    assert settings.mcp_host == host


@pytest.mark.parametrize("port", [0, 65536, -1])
def test_mcp_settings_reject_out_of_range_ports(port):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, mcp_port=port)


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
