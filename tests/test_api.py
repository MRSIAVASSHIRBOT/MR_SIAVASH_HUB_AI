from fastapi.testclient import TestClient

from mrhub.config import get_settings
from mrhub.main import create_app


def test_health_endpoint() -> None:
    client = TestClient(create_app())
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_task_create_and_read(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("MRH_DATABASE_PATH", str(tmp_path / "test.sqlite3"))
    get_settings.cache_clear()
    client = TestClient(create_app())

    created = client.post(
        "/tasks",
        json={
            "task_type": "demo.echo",
            "description": "A harmless task record",
        },
    )
    assert created.status_code == 201
    task = created.json()
    assert task["status"] == "queued"

    fetched = client.get(f"/tasks/{task['task_id']}")
    assert fetched.status_code == 200
    assert fetched.json()["task_id"] == task["task_id"]
    get_settings.cache_clear()


def test_task_type_validation() -> None:
    client = TestClient(create_app())
    response = client.post("/tasks", json={"task_type": "bad task name"})
    assert response.status_code == 422
