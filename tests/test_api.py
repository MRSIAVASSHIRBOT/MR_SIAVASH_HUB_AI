from fastapi.testclient import TestClient

from client_helpers import authenticated_client
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
    client = authenticated_client()

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
    client = authenticated_client()
    response = client.post("/tasks", json={"task_type": "bad task name"})
    assert response.status_code == 422


def test_jobs_summary_reports_queue_without_starting_worker(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("MRH_DATABASE_PATH", str(tmp_path / "test.sqlite3"))
    get_settings.cache_clear()
    client = authenticated_client()
    created = client.post(
        "/tasks", json={"task_type": "demo.echo", "description": "queued task"}
    )
    assert created.status_code == 201

    response = client.get("/jobs/summary")
    assert response.status_code == 200
    body = response.json()
    assert body["total_tasks"] == 1
    assert body["status_counts"]["queued"] == 1
    assert body["registered_handlers"] == ["demo.echo"]
    assert body["execution_mode"] == "pull_driven"
    assert body["automatic_execution"] is False
    get_settings.cache_clear()


def test_jobs_summary_requires_authentication(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("MRH_DATABASE_PATH", str(tmp_path / "test.sqlite3"))
    get_settings.cache_clear()
    response = TestClient(create_app()).get("/jobs/summary")
    assert response.status_code in (401, 403)
    get_settings.cache_clear()


def test_task_result_endpoint_distinguishes_pending_and_completed(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("MRH_DATABASE_PATH", str(tmp_path / "test.sqlite3"))
    get_settings.cache_clear()
    client = authenticated_client()
    created = client.post(
        "/tasks", json={"task_type": "demo.echo", "description": "result payload"}
    )
    task_id = created.json()["task_id"]

    pending = client.get(f"/tasks/{task_id}/result")
    assert pending.status_code == 409

    from mrhub.infrastructure.database import TaskRepository
    from mrhub.jobs.worker import WorkerEngine

    repository = TaskRepository(tmp_path / "test.sqlite3")
    repository.initialize()
    completed = WorkerEngine(repository).run_once()
    assert completed is not None

    response = client.get(f"/tasks/{task_id}/result")
    assert response.status_code == 200
    assert response.json()["result"] == {
        "message": "result payload",
        "task_type": "demo.echo",
    }
    assert response.json()["attempt_count"] == 1
    get_settings.cache_clear()


def test_task_result_endpoint_returns_not_found_for_unknown_task(tmp_path, monkeypatch) -> None:
    from uuid import uuid4

    monkeypatch.setenv("MRH_DATABASE_PATH", str(tmp_path / "test.sqlite3"))
    get_settings.cache_clear()
    client = authenticated_client()
    response = client.get(f"/tasks/{uuid4()}/result")
    assert response.status_code == 404
    get_settings.cache_clear()
