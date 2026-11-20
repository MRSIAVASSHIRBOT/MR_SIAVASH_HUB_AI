from __future__ import annotations

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


def _paired_device(client, *, scopes=None):
    device_id = str(uuid4())
    requested_scopes = scopes or ["device.heartbeat", "app.launch", "screen.capture"]
    challenge = client.post("/devices/pairing-challenges", json={
        "device_id": device_id,
        "platform": "windows",
        "label": "Windows companion",
        "advertised_capabilities": ["device.heartbeat", "app.launch", "screen.capture"],
        "scopes": requested_scopes,
    })
    assert challenge.status_code == 201
    exchanged = client.post("/devices/pair", json={
        "pairing_code": challenge.json()["pairing_code"],
        "device_id": device_id,
        "agent_version": "0.1.0",
        "os_version": "Windows 11",
    })
    assert exchanged.status_code == 200
    tokens = exchanged.json()
    return device_id, {
        "Authorization": f"Bearer {tokens['access_token']}",
        "X-Device-ID": device_id,
    }


def test_owner_can_submit_and_paired_device_can_claim_allowlisted_app_launch(tmp_path, monkeypatch):
    client, _ = _owner_client(tmp_path, monkeypatch)
    device_id, device_headers = _paired_device(client)

    submitted = client.post(
        f"/devices/{device_id}/tasks",
        headers={"Idempotency-Key": "launch-notepad-0001"},
        json={"action": "app.launch", "app": "notepad", "timeout_seconds": 30},
    )
    assert submitted.status_code == 201
    task = submitted.json()
    assert task["status"] == "queued"
    assert task["required_scope"] == "app.launch"
    assert task["action"] == "app.launch"
    assert task["app"] == "notepad"

    claimed = client.post("/devices/tasks/claim", headers=device_headers)
    assert claimed.status_code == 200
    envelope = claimed.json()
    assert envelope["task"]["task_id"] == task["task_id"]
    assert envelope["task"]["app"] == "notepad"
    assert len(envelope["lease_token"]) >= 40
    assert client.post("/devices/tasks/claim", headers=device_headers).json()["task"] is None
    get_settings.cache_clear()


def test_device_task_idempotency_returns_same_task_and_rejects_key_reuse(tmp_path, monkeypatch):
    client, _ = _owner_client(tmp_path, monkeypatch)
    device_id, _ = _paired_device(client)
    headers = {"Idempotency-Key": "launch-idempotent-0001"}
    payload = {"action": "app.launch", "app": "calculator"}

    first = client.post(f"/devices/{device_id}/tasks", headers=headers, json=payload)
    replay = client.post(f"/devices/{device_id}/tasks", headers=headers, json=payload)
    conflict = client.post(
        f"/devices/{device_id}/tasks",
        headers=headers,
        json={"action": "app.launch", "app": "notepad"},
    )
    assert first.status_code == 201
    assert replay.status_code == 200
    assert replay.json()["task_id"] == first.json()["task_id"]
    assert conflict.status_code == 409
    get_settings.cache_clear()


def test_device_task_requires_owner_and_explicit_device_scope(tmp_path, monkeypatch):
    client, _ = _owner_client(tmp_path, monkeypatch)
    device_id, device_headers = _paired_device(client, scopes=["device.heartbeat"])
    denied = client.post(
        f"/devices/{device_id}/tasks",
        headers={"Idempotency-Key": "launch-no-scope-0001"},
        json={"action": "app.launch", "app": "notepad"},
    )
    assert denied.status_code == 403
    assert client.post("/devices/tasks/claim", headers=device_headers).status_code == 200
    get_settings.cache_clear()


def test_device_task_rejects_unbounded_or_unknown_actions(tmp_path, monkeypatch):
    client, _ = _owner_client(tmp_path, monkeypatch)
    device_id, _ = _paired_device(client)
    invalid_action = client.post(
        f"/devices/{device_id}/tasks",
        headers={"Idempotency-Key": "bad-action-0000001"},
        json={"action": "shell.execute", "command": "whoami"},
    )
    invalid_app = client.post(
        f"/devices/{device_id}/tasks",
        headers={"Idempotency-Key": "bad-app-0000000001"},
        json={"action": "app.launch", "app": "powershell"},
    )
    extra = client.post(
        f"/devices/{device_id}/tasks",
        headers={"Idempotency-Key": "extra-field-0000001"},
        json={"action": "screen.capture", "screenshot_destination": "https://example.invalid"},
    )
    assert invalid_action.status_code == 422
    assert invalid_app.status_code == 422
    assert extra.status_code == 422
    get_settings.cache_clear()


def test_outcome_requires_the_claim_lease_and_is_reported_not_verified(tmp_path, monkeypatch):
    client, _ = _owner_client(tmp_path, monkeypatch)
    device_id, device_headers = _paired_device(client)
    submitted = client.post(
        f"/devices/{device_id}/tasks",
        headers={"Idempotency-Key": "launch-result-000001"},
        json={"action": "app.launch", "app": "calculator"},
    )
    claimed = client.post("/devices/tasks/claim", headers=device_headers).json()
    task_id = submitted.json()["task_id"]

    rejected = client.post(
        f"/devices/tasks/{task_id}/outcome",
        headers=device_headers,
        json={"lease_token": "incorrect-lease-token-value-000000000000", "outcome": "succeeded"},
    )
    accepted = client.post(
        f"/devices/tasks/{task_id}/outcome",
        headers=device_headers,
        json={"lease_token": claimed["lease_token"], "outcome": "succeeded", "duration_ms": 250},
    )
    duplicate = client.post(
        f"/devices/tasks/{task_id}/outcome",
        headers=device_headers,
        json={"lease_token": claimed["lease_token"], "outcome": "succeeded", "duration_ms": 250},
    )
    owner_view = client.get(f"/devices/{device_id}/tasks/{task_id}")
    assert rejected.status_code == 409
    assert accepted.status_code == 200
    assert accepted.json()["status"] == "reported_succeeded"
    assert duplicate.status_code == 409
    assert owner_view.json()["status"] == "reported_succeeded"
    assert owner_view.json()["outcome_verified"] is False
    get_settings.cache_clear()


def test_expired_claim_becomes_unknown_outcome_and_is_never_replayed(tmp_path, monkeypatch):
    client, database_path = _owner_client(tmp_path, monkeypatch)
    device_id, device_headers = _paired_device(client)
    submitted = client.post(
        f"/devices/{device_id}/tasks",
        headers={"Idempotency-Key": "launch-expiry-000001"},
        json={"action": "app.launch", "app": "notepad"},
    )
    task_id = submitted.json()["task_id"]
    claimed = client.post("/devices/tasks/claim", headers=device_headers)
    assert claimed.status_code == 200
    with sqlite3.connect(database_path) as db:
        db.execute(
            "UPDATE personal_device_tasks SET lease_expires_at='2000-01-01T00:00:00+00:00' WHERE task_id=?",
            (task_id,),
        )
    next_claim = client.post("/devices/tasks/claim", headers=device_headers)
    owner_view = client.get(f"/devices/{device_id}/tasks/{task_id}")
    assert next_claim.json()["task"] is None
    assert owner_view.json()["status"] == "unknown_outcome"
    get_settings.cache_clear()


def test_owner_can_cancel_queued_task_but_not_claimed_task(tmp_path, monkeypatch):
    client, _ = _owner_client(tmp_path, monkeypatch)
    device_id, device_headers = _paired_device(client)
    queued = client.post(
        f"/devices/{device_id}/tasks",
        headers={"Idempotency-Key": "launch-cancel-queued-001"},
        json={"action": "app.launch", "app": "notepad"},
    )
    cancelled = client.delete(f"/devices/{device_id}/tasks/{queued.json()['task_id']}")
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"

    active = client.post(
        f"/devices/{device_id}/tasks",
        headers={"Idempotency-Key": "launch-cancel-active-001"},
        json={"action": "app.launch", "app": "calculator"},
    )
    assert client.post("/devices/tasks/claim", headers=device_headers).json()["task"]["task_id"] == active.json()["task_id"]
    refused = client.delete(f"/devices/{device_id}/tasks/{active.json()['task_id']}")
    assert refused.status_code == 409
    get_settings.cache_clear()

def test_screen_capture_requires_explicit_owner_confirmation_and_scope(tmp_path, monkeypatch):
    client, _ = _owner_client(tmp_path, monkeypatch)
    device_id, _ = _paired_device(client)
    headers = {"Idempotency-Key": "screen-capture-00001"}
    unconfirmed = client.post(
        f"/devices/{device_id}/tasks",
        headers=headers,
        json={"action": "screen.capture"},
    )
    confirmed = client.post(
        f"/devices/{device_id}/tasks",
        headers=headers,
        json={"action": "screen.capture", "confirm_sensitive_action": True},
    )
    assert unconfirmed.status_code == 422
    assert confirmed.status_code == 201
    assert confirmed.json()["required_scope"] == "screen.capture"
    get_settings.cache_clear()

