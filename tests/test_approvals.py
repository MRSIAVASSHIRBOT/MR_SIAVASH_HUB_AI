from fastapi.testclient import TestClient

from mrhub.config import get_settings
from mrhub.infrastructure.database import TaskRepository
from mrhub.main import create_app


def make_authenticated_client(tmp_path, monkeypatch) -> TestClient:
    database_path = tmp_path / "approvals.sqlite3"
    monkeypatch.setenv("MRH_DATABASE_PATH", str(database_path))
    get_settings.cache_clear()
    client = TestClient(create_app())
    password = "test-only-strong-password-2026"
    setup = client.post("/auth/setup", json={"password": password})
    assert setup.status_code == 201
    login = client.post(
        "/auth/login",
        json={"username": "owner", "password": password},
    )
    assert login.status_code == 200
    client.headers.update(
        {"Authorization": f"Bearer {login.json()['access_token']}"}
    )
    return client


def test_owner_can_approve_pending_task_and_decision_is_audited(tmp_path, monkeypatch) -> None:
    client = make_authenticated_client(tmp_path, monkeypatch)
    created = client.post(
        "/tasks",
        json={"task_type": "external.publish", "description": "Publish reviewed content"},
    )
    assert created.status_code == 201
    task_id = created.json()["task_id"]
    assert created.json()["status"] == "waiting_approval"

    response = client.post(
        f"/tasks/{task_id}/approval",
        json={"decision": "approved", "reason": "Reviewed by owner"},
    )
    assert response.status_code == 201
    approval = response.json()
    assert approval["decision"] == "approved"
    assert approval["approver_id"] == "local-owner"
    assert len(approval["action_fingerprint"]) == 64

    task = client.get(f"/tasks/{task_id}")
    assert task.json()["status"] == "queued"
    persisted = client.get(f"/tasks/{task_id}/approval")
    assert persisted.status_code == 200
    assert persisted.json()["approval_id"] == approval["approval_id"]

    repository = TaskRepository(tmp_path / "approvals.sqlite3")
    events = repository.list_audit()
    assert any(
        event["event_type"] == "task.approval_decided"
        and event["outcome"] == "approved"
        and event["actor_type"] == "user"
        and event["actor_id"] == "local-owner"
        for event in events
    )


def test_rejected_approval_moves_task_to_rejected_terminal_state(tmp_path, monkeypatch) -> None:
    client = make_authenticated_client(tmp_path, monkeypatch)
    created = client.post(
        "/tasks",
        json={"task_type": "external.delete", "description": "Delete external resource"},
    )
    task_id = created.json()["task_id"]
    response = client.post(
        f"/tasks/{task_id}/approval",
        json={"decision": "rejected", "reason": "Not authorized"},
    )
    assert response.status_code == 201
    assert client.get(f"/tasks/{task_id}").json()["status"] == "rejected"


def test_approval_requires_authentication_and_rejects_duplicate_decisions(
    tmp_path, monkeypatch
) -> None:
    client = make_authenticated_client(tmp_path, monkeypatch)
    created = client.post(
        "/tasks",
        json={"task_type": "external.publish", "description": "Publish"},
    )
    task_id = created.json()["task_id"]
    token = client.headers.pop("Authorization")
    unauthenticated = client.post(
        f"/tasks/{task_id}/approval",
        json={"decision": "approved"},
    )
    assert unauthenticated.status_code == 401
    client.headers["Authorization"] = token

    first = client.post(
        f"/tasks/{task_id}/approval",
        json={"decision": "approved"},
    )
    assert first.status_code == 201
    second = client.post(
        f"/tasks/{task_id}/approval",
        json={"decision": "rejected"},
    )
    assert second.status_code == 409


def test_non_pending_task_cannot_be_approved(tmp_path, monkeypatch) -> None:
    client = make_authenticated_client(tmp_path, monkeypatch)
    created = client.post(
        "/tasks",
        json={"task_type": "demo.echo", "description": "Low-risk task"},
    )
    task_id = created.json()["task_id"]
    response = client.post(
        f"/tasks/{task_id}/approval",
        json={"decision": "approved"},
    )
    assert response.status_code == 409
