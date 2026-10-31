from fastapi.testclient import TestClient

from mrhub.config import get_settings
from mrhub.main import create_app


def test_high_risk_task_waits_for_approval(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("MRH_DATABASE_PATH", str(tmp_path / "approval.sqlite3"))
    get_settings.cache_clear()
    client = TestClient(create_app())
    response = client.post(
        "/tasks",
        json={"task_type": "content.publish", "risk_class": "high"},
    )
    assert response.status_code == 201
    assert response.json()["status"] == "waiting_approval"
    get_settings.cache_clear()


def test_prohibited_task_is_rejected(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("MRH_DATABASE_PATH", str(tmp_path / "deny.sqlite3"))
    get_settings.cache_clear()
    client = TestClient(create_app())
    response = client.post(
        "/tasks",
        json={"task_type": "restricted.action", "risk_class": "prohibited"},
    )
    assert response.status_code == 403
    get_settings.cache_clear()


def test_job_cancel_endpoint(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("MRH_DATABASE_PATH", str(tmp_path / "cancel.sqlite3"))
    get_settings.cache_clear()
    client = TestClient(create_app())
    created = client.post("/tasks", json={"task_type": "demo.task"})
    task_id = created.json()["task_id"]
    cancelled = client.post(f"/jobs/{task_id}/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    get_settings.cache_clear()
