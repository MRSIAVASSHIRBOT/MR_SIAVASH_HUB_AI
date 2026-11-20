from datetime import UTC, datetime, timedelta
import sqlite3
from uuid import uuid4

from fastapi.testclient import TestClient

from mrhub.config import get_settings
from mrhub.main import create_app


def _owner_client(tmp_path, monkeypatch):
    database_path = tmp_path / "device-tasks.sqlite3"
    monkeypatch.setenv("MRH_DATABASE_PATH", str(database_path))
    get_settings.cache_clear()
    client = TestClient(create_app())
    password = "test-only-strong-password-2026"
    assert client.post("/auth/setup", json={"password": password}).status_code == 201
    login = client.post("/auth/login", json={"username": "owner", "password": password})
    assert login.status_code == 200
    client.headers.update({"Authorization": f"Bearer {login.json()['access_token']}"})
    return client, database_path


def _paired_device(client, scopes=None):
    payload = {
        "device_id": str(uuid4()),
        "platform": "windows",
        "label": "Windows task dispatch test",
        "advertised_capabilities": ["device.heartbeat", "app.launch"],
        "scopes": scopes or ["device.heartbeat", "app.launch"],
    }
    challenge = client.post("/devices/pairing-challenges", json=payload)
    assert challenge.status_code == 201
    exchange = client.post("/devices/pair", json={
        "pairing_code": challenge.json()["pairing_code"],
        "device_id": payload["device_id"],
        "agent_version": "0.2.0",
        "os_version": "Windows 11",
    })
    assert exchange.status_code == 200
    return payload["device_id"], exchange.json()


def _device_headers(device_id, tokens):
    return {
        "Authorization": f"Bearer {tokens['access_token']}",
        "X-Device-ID": device_id,
    }


def _create_task(client, device_id, *, app_alias="chatgpt", key=None, scheduled_at=None, expires=300):
    return client.post(f"/devices/{device_id}/tasks", json={
        "action": "launch_app",
        "app_alias": app_alias,
        "idempotency_key": key or str(uuid4()),
        "scheduled_at": scheduled_at or datetime.now(UTC).isoformat(),
        "expires_in_seconds": expires,
    })


def test_owner_task_create_is_scoped_and_idempotent(tmp_path, monkeypatch):
    client, _ = _owner_client(tmp_path, monkeypatch)
    device_id, _tokens = _paired_device(client)
    key = str(uuid4())
    run_at = datetime.now(UTC).isoformat()
    first = _create_task(client, device_id, key=key, scheduled_at=run_at)
    second = _create_task(client, device_id, key=key, scheduled_at=run_at)
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["task"]["task_id"] == second.json()["task"]["task_id"]
    conflict = _create_task(client, device_id, app_alias="notepad", key=key, scheduled_at=run_at)
    assert conflict.status_code == 409
    assert client.get(f"/devices/{device_id}/tasks").json()["count"] == 1
    get_settings.cache_clear()


def test_owner_cannot_dispatch_to_device_without_app_launch_scope(tmp_path, monkeypatch):
    client, _ = _owner_client(tmp_path, monkeypatch)
    device_id, _tokens = _paired_device(client, scopes=["device.heartbeat"])
    response = _create_task(client, device_id)
    assert response.status_code == 403
    get_settings.cache_clear()


def test_device_claims_only_due_task_and_reports_verified_outcome(tmp_path, monkeypatch):
    client, database_path = _owner_client(tmp_path, monkeypatch)
    device_id, tokens = _paired_device(client)
    future = (datetime.now(UTC) + timedelta(minutes=5)).isoformat()
    created = _create_task(client, device_id, scheduled_at=future)
    assert created.status_code == 201
    headers = _device_headers(device_id, tokens)
    not_due = client.post("/devices/tasks/claim", headers=headers)
    assert not_due.status_code == 200
    assert not_due.json()["task"] is None

    with sqlite3.connect(database_path) as db:
        db.execute(
            "UPDATE personal_device_tasks SET available_at=? WHERE task_id=?",
            ("2000-01-01T00:00:00+00:00", created.json()["task"]["task_id"]),
        )
    claimed = client.post("/devices/tasks/claim", headers=headers)
    task = claimed.json()["task"]
    assert task["status"] == "claimed"
    assert task["app_alias"] == "chatgpt"
    assert task["attempt_count"] == 1

    completed = client.post(f"/devices/tasks/{task['task_id']}/complete", headers=headers, json={
        "outcome": "succeeded", "result_code": "launched",
    })
    assert completed.status_code == 200
    assert completed.json()["task"]["status"] == "succeeded"
    assert client.post(f"/devices/tasks/{task['task_id']}/complete", headers=headers, json={
        "outcome": "succeeded", "result_code": "launched",
    }).status_code == 409

    listed = client.get(f"/devices/{device_id}/tasks").json()["tasks"]
    assert listed[0]["result_code"] == "launched"
    with sqlite3.connect(database_path) as db:
        events = {row[0] for row in db.execute(
            "SELECT event_type FROM audit_events WHERE subject_id=?",
            (task["task_id"],),
        )}
    assert {"device.task_created", "device.task_claimed", "device.task_completed"}.issubset(events)
    get_settings.cache_clear()


def test_claimed_task_is_not_replayed_after_lease_expiry(tmp_path, monkeypatch):
    client, database_path = _owner_client(tmp_path, monkeypatch)
    device_id, tokens = _paired_device(client)
    created = _create_task(client, device_id)
    headers = _device_headers(device_id, tokens)
    claimed = client.post("/devices/tasks/claim", headers=headers).json()["task"]
    with sqlite3.connect(database_path) as db:
        db.execute(
            "UPDATE personal_device_tasks SET lease_expires_at=? WHERE task_id=?",
            ("2000-01-01T00:00:00+00:00", claimed["task_id"]),
        )
    completed = client.post(f"/devices/tasks/{claimed['task_id']}/complete", headers=headers, json={
        "outcome": "succeeded", "result_code": "launched",
    })
    assert completed.status_code == 200
    assert completed.json()["task"]["status"] == "delivery_unknown"
    assert client.post("/devices/tasks/claim", headers=headers).json()["task"] is None
    get_settings.cache_clear()


def test_owner_can_cancel_queued_task_but_not_claimed_task(tmp_path, monkeypatch):
    client, _ = _owner_client(tmp_path, monkeypatch)
    device_id, tokens = _paired_device(client)
    queued = _create_task(client, device_id).json()["task"]
    cancelled = client.delete(f"/devices/{device_id}/tasks/{queued['task_id']}")
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"

    claimed_task = _create_task(client, device_id).json()["task"]
    headers = _device_headers(device_id, tokens)
    claimed = client.post("/devices/tasks/claim", headers=headers).json()["task"]
    assert claimed["task_id"] == claimed_task["task_id"]
    denied = client.delete(f"/devices/{device_id}/tasks/{claimed['task_id']}")
    assert denied.status_code == 409
    assert "only queued tasks" in denied.json()["detail"]
    get_settings.cache_clear()


def test_device_scope_is_required_for_claim_and_completion(tmp_path, monkeypatch):
    client, _ = _owner_client(tmp_path, monkeypatch)
    device_id, tokens = _paired_device(client, scopes=["device.heartbeat"])
    headers = _device_headers(device_id, tokens)
    assert client.post("/devices/tasks/claim", headers=headers).status_code == 403
    get_settings.cache_clear()


def test_revocation_cancels_queued_tasks_and_marks_claimed_unknown(tmp_path, monkeypatch):
    client, _ = _owner_client(tmp_path, monkeypatch)
    device_id, tokens = _paired_device(client)
    queued = _create_task(client, device_id).json()["task"]
    claimed_task = _create_task(client, device_id, app_alias="notepad").json()["task"]
    headers = _device_headers(device_id, tokens)
    claimed = client.post("/devices/tasks/claim", headers=headers).json()["task"]
    assert claimed["task_id"] == queued["task_id"]

    revoked = client.delete(f"/devices/{device_id}")
    assert revoked.status_code == 200
    tasks = {item["task_id"]: item for item in client.get(f"/devices/{device_id}/tasks").json()["tasks"]}
    assert tasks[queued["task_id"]]["status"] == "delivery_unknown"
    assert tasks[claimed_task["task_id"]]["status"] == "cancelled"
    get_settings.cache_clear()


def test_queued_task_expiry_is_reconciled_and_audited(tmp_path, monkeypatch):
    client, database_path = _owner_client(tmp_path, monkeypatch)
    device_id, _tokens = _paired_device(client)
    created = _create_task(client, device_id).json()["task"]
    with sqlite3.connect(database_path) as db:
        db.execute(
            "UPDATE personal_device_tasks SET expires_at=? WHERE task_id=?",
            ("2000-01-01T00:00:00+00:00", created["task_id"]),
        )
    listed = client.get(f"/devices/{device_id}/tasks").json()["tasks"]
    assert listed[0]["status"] == "expired"
    assert listed[0]["result_code"] == "expired"
    with sqlite3.connect(database_path) as db:
        event = db.execute(
            "SELECT event_type FROM audit_events WHERE subject_id=? AND event_type='device.task_expired'",
            (created["task_id"],),
        ).fetchone()
    assert event is not None
    get_settings.cache_clear()
