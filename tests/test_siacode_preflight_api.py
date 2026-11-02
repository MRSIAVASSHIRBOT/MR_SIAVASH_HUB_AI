from fastapi.testclient import TestClient

from client_helpers import authenticated_client
from mrhub.config import get_settings
from mrhub.main import create_app


def test_siacode_preflight_endpoint_requires_authentication(monkeypatch, tmp_path):
    monkeypatch.setenv("MRH_DATABASE_PATH", str(tmp_path / "siacode-api.sqlite3"))
    monkeypatch.setenv("MRH_SIACODE_ENABLED", "false")
    get_settings.cache_clear()
    response = TestClient(create_app()).post("/models/providers/siacode/preflight")
    assert response.status_code in (401, 403)
    get_settings.cache_clear()


def test_siacode_preflight_endpoint_is_disabled_by_default(monkeypatch):
    monkeypatch.setenv("MRH_SIACODE_ENABLED", "false")
    monkeypatch.delenv("MRH_SIACODE_BASE_URL", raising=False)
    get_settings.cache_clear()
    client = authenticated_client()

    response = client.post("/models/providers/siacode/preflight")

    assert response.status_code == 200
    assert response.json() == {
        "state": "disabled",
        "ready": False,
        "reason_code": "disabled",
        "coding_requests_enabled": False,
        "external_actions_started": False,
    }
    get_settings.cache_clear()


def test_siacode_preflight_endpoint_rejects_remote_hosts_without_network(monkeypatch):
    monkeypatch.setenv("MRH_SIACODE_ENABLED", "true")
    monkeypatch.setenv("MRH_SIACODE_BASE_URL", "https://example.com")
    get_settings.cache_clear()
    client = authenticated_client()

    response = client.post("/models/providers/siacode/preflight")

    assert response.status_code == 200
    body = response.json()
    assert body["state"] == "unconfigured"
    assert body["ready"] is False
    assert body["reason_code"] == "invalid_or_missing_config"
    assert body["coding_requests_enabled"] is False
    assert body["external_actions_started"] is False
    assert "example.com" not in str(body)
    get_settings.cache_clear()
