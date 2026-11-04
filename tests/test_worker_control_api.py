"""Authenticated API coverage for the durable worker emergency stop."""

from fastapi.testclient import TestClient

from client_helpers import authenticated_client
from mrhub.config import get_settings
from mrhub.main import create_app


def test_worker_control_endpoints_require_authentication(tmp_path, monkeypatch):
    monkeypatch.setenv("MRH_DATABASE_PATH", str(tmp_path / "worker-control-api.sqlite3"))
    get_settings.cache_clear()
    client = TestClient(create_app())

    assert client.get("/jobs/control").status_code in (401, 403)
    assert client.post("/jobs/emergency-stop", json={"reason": "maintenance"}).status_code in (
        401,
        403,
    )
    assert client.post("/jobs/resume").status_code in (401, 403)
    get_settings.cache_clear()


def test_emergency_stop_and_resume_persist_owner_attribution(tmp_path, monkeypatch):
    monkeypatch.setenv("MRH_DATABASE_PATH", str(tmp_path / "worker-control-api.sqlite3"))
    get_settings.cache_clear()
    client = authenticated_client()

    before = client.get("/jobs/control")
    assert before.status_code == 200
    assert before.json()["stopped"] is False

    stopped = client.post("/jobs/emergency-stop", json={"reason": "Scheduled maintenance"})
    assert stopped.status_code == 200
    stop_body = stopped.json()
    assert stop_body["stopped"] is True
    assert stop_body["reason"] == "Scheduled maintenance"
    assert stop_body["changed_by"]
    owner_id = stop_body["changed_by"]

    persisted = client.get("/jobs/control")
    assert persisted.status_code == 200
    assert persisted.json()["stopped"] is True
    assert persisted.json()["changed_by"] == owner_id

    resumed = client.post("/jobs/resume")
    assert resumed.status_code == 200
    assert resumed.json()["stopped"] is False
    assert resumed.json()["reason"] is None
    assert resumed.json()["changed_by"] == owner_id

    get_settings.cache_clear()


def test_emergency_stop_rejects_blank_reason(tmp_path, monkeypatch):
    monkeypatch.setenv("MRH_DATABASE_PATH", str(tmp_path / "worker-control-api.sqlite3"))
    get_settings.cache_clear()
    client = authenticated_client()

    response = client.post("/jobs/emergency-stop", json={"reason": "   "})
    assert response.status_code == 422
    assert response.json()["detail"] == "Stop reason must not be blank"
    get_settings.cache_clear()
