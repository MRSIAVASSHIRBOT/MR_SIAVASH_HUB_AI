from fastapi.testclient import TestClient

from client_helpers import authenticated_client
from mrhub.config import get_settings
from mrhub.main import create_app


def test_local_integration_status_routes_require_authentication(tmp_path, monkeypatch):
    monkeypatch.setenv("MRH_DATABASE_PATH", str(tmp_path / "integration-auth.sqlite3"))
    get_settings.cache_clear()
    try:
        client = TestClient(create_app())
        for path in (
            "/integrations/assistant-gateway/status",
            "/integrations/code-engine/status",
        ):
            response = client.get(path)
            assert response.status_code == 401
    finally:
        get_settings.cache_clear()


def test_both_local_integrations_are_disabled_by_default_without_probing(tmp_path, monkeypatch):
    monkeypatch.setenv("MRH_DATABASE_PATH", str(tmp_path / "integration-defaults.sqlite3"))
    monkeypatch.delenv("MRH_ASSISTANT_GATEWAY_ENABLED", raising=False)
    monkeypatch.delenv("MRH_CODE_ENGINE_ENABLED", raising=False)
    get_settings.cache_clear()

    from mrhub.integrations import assistant_gateway, code_engine

    def unexpected_probe(*args, **kwargs):
        raise AssertionError("disabled integrations must not issue network probes")

    monkeypatch.setattr(assistant_gateway, "probe_loopback_service", unexpected_probe)
    monkeypatch.setattr(code_engine, "probe_loopback_service", unexpected_probe)
    try:
        client = authenticated_client()
        assistant = client.get("/integrations/assistant-gateway/status")
        code = client.get("/integrations/code-engine/status")
        assert assistant.status_code == 200
        assert code.status_code == 200
        assert assistant.json() == {
            "contract_version": "1.0",
            "status": "disabled",
            "configured": False,
        }
        assert code.json() == {"contract_version": "1.0", "status": "disabled", "configured": False}
        assert "base_url" not in assistant.text
        assert "base_url" not in code.text
    finally:
        get_settings.cache_clear()


def test_assistant_gateway_status_uses_shared_bounded_probe_and_sanitizes_result(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("MRH_DATABASE_PATH", str(tmp_path / "assistant-status.sqlite3"))
    monkeypatch.setenv("MRH_ASSISTANT_GATEWAY_ENABLED", "true")
    monkeypatch.setenv("MRH_ASSISTANT_GATEWAY_BASE_URL", "http://127.0.0.1:18789")
    get_settings.cache_clear()

    from mrhub.integrations import assistant_gateway

    calls = []

    async def fake_probe(base_url, health_path, *, timeout_seconds, max_response_bytes):
        calls.append((base_url, health_path, timeout_seconds, max_response_bytes))
        return {
            "contract_version": "1.0",
            "status": "reachable",
            "configured": True,
            "http_status": 200,
        }

    monkeypatch.setattr(assistant_gateway, "probe_loopback_service", fake_probe)
    try:
        response = authenticated_client().get("/integrations/assistant-gateway/status")
        assert response.status_code == 200
        assert response.json() == {
            "contract_version": "1.0",
            "status": "reachable",
            "configured": True,
            "http_status": 200,
        }
        assert calls == [("http://127.0.0.1:18789", "/health", 2.0, 8192)]
        assert "127.0.0.1" not in response.text
    finally:
        get_settings.cache_clear()


def test_code_engine_status_uses_shared_bounded_probe_and_sanitizes_result(tmp_path, monkeypatch):
    monkeypatch.setenv("MRH_DATABASE_PATH", str(tmp_path / "code-status.sqlite3"))
    monkeypatch.setenv("MRH_CODE_ENGINE_ENABLED", "true")
    monkeypatch.setenv("MRH_CODE_ENGINE_BASE_URL", "http://[::1]:9123")
    monkeypatch.setenv("MRH_CODE_ENGINE_TIMEOUT_SECONDS", "3.5")
    monkeypatch.setenv("MRH_CODE_ENGINE_MAX_RESPONSE_BYTES", "4096")
    get_settings.cache_clear()

    from mrhub.integrations import code_engine

    calls = []

    async def fake_probe(base_url, health_path, *, timeout_seconds, max_response_bytes):
        calls.append((base_url, health_path, timeout_seconds, max_response_bytes))
        return {"contract_version": "1.0", "status": "unreachable", "configured": True}

    monkeypatch.setattr(code_engine, "probe_loopback_service", fake_probe)
    try:
        response = authenticated_client().get("/integrations/code-engine/status")
        assert response.status_code == 200
        assert response.json() == {
            "contract_version": "1.0",
            "status": "unreachable",
            "configured": True,
        }
        assert calls == [("http://[::1]:9123", "/health", 3.5, 4096)]
        assert "::1" not in response.text
    finally:
        get_settings.cache_clear()


def test_capability_discovery_lists_both_integrations_without_probing(tmp_path, monkeypatch):
    monkeypatch.setenv("MRH_DATABASE_PATH", str(tmp_path / "integration-catalog.sqlite3"))
    monkeypatch.setenv("MRH_ASSISTANT_GATEWAY_ENABLED", "true")
    monkeypatch.setenv("MRH_ASSISTANT_GATEWAY_BASE_URL", "http://127.0.0.1:18789")
    monkeypatch.setenv("MRH_CODE_ENGINE_ENABLED", "true")
    monkeypatch.setenv("MRH_CODE_ENGINE_BASE_URL", "http://127.0.0.1:9123")
    get_settings.cache_clear()

    from mrhub.integrations import assistant_gateway, code_engine

    def unexpected_probe(*args, **kwargs):
        raise AssertionError("capability discovery must remain read-only")

    monkeypatch.setattr(assistant_gateway, "probe_loopback_service", unexpected_probe)
    monkeypatch.setattr(code_engine, "probe_loopback_service", unexpected_probe)
    try:
        response = authenticated_client().get("/agent/capabilities")
        assert response.status_code == 200
        body = response.json()
        assert body["integration_contract_version"] == "1.0"
        assert body["integrations"]["assistant_gateway"] == {
            "enabled": True,
            "configured": True,
            "health_status": "not_checked",
            "status_endpoint": "/integrations/assistant-gateway/status",
        }
        assert body["integrations"]["code_engine"] == {
            "enabled": True,
            "configured": True,
            "health_status": "not_checked",
            "status_endpoint": "/integrations/code-engine/status",
        }
        assert body["network_probes_performed"] is False
        assert body["execution_started"] is False
        assert "127.0.0.1" not in response.text
    finally:
        get_settings.cache_clear()
