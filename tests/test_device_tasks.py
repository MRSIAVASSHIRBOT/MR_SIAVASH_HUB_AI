from __future__ import annotations

import hashlib
import sqlite3
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from mrhub.config import get_settings
from mrhub.devices.tasks import DeviceTaskNotFound, DeviceTaskPermissionError, DeviceTaskRepository
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
    requested_scopes = scopes or [
        "device.heartbeat",
        "app.launch",
        "screen.capture",
    ]
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
    headers = {
        "Authorization": f"Bearer {tokens['access_token']}",
        "X-Device-ID": device_id,
    }
    return device_id, headers


def _submit(client, device_id, *, action="app.launch", app="notepad", key=None, **extra):
    payload = {"action": action, **extra}
    if app is not None:
        payload["app"] = app
    headers = {"Idempotency-Key": key or f"device-task-{uuid4()}"}
    return client.post(f"/devices/{device_id}/tasks", headers=headers, json=payload)


def test_owner_can_submit_scheduled_task_and_device_claims_it_once(tmp_path, monkeypatch):
    client, database_path = _owner_client(tmp_path, monkeypatch)
    device_id, device_headers = _paired_device(client)
    future = (datetime.now(UTC) + timedelta(minutes=5)).isoformat()
    submitted = _submit(
        client,
        device_id,
        app="notepad",
        key="launch-notepad-0001",
        scheduled_at=future,
    )
    assert submitted.status_code == 201
    task = submitted.json()["task"]
    assert task["status"] == "queued"
    assert task["required_scope"] == "app.launch"
    assert task["scheduled_at"] == future

    not_due = client.post("/devices/tasks/claim", headers=device_headers)
    assert not_due.status_code == 200
    assert not_due.json()["task"] is None

    with sqlite3.connect(database_path) as db:
        db.execute(
            "UPDATE personal_device_tasks SET scheduled_at=? WHERE task_id=?",
            ("2000-01-01T00:00:00+00:00", task["task_id"]),
        )
    claimed = client.post("/devices/tasks/claim", headers=device_headers)
    envelope = claimed.json()
    assert envelope["task"]["task_id"] == task["task_id"]
    assert envelope["task"]["attempt_count"] == 1
    assert len(envelope["lease_token"]) >= 40
    assert client.post("/devices/tasks/claim", headers=device_headers).json()["task"] is None
    get_settings.cache_clear()


def test_idempotency_is_owner_scoped_hashed_and_rejects_payload_reuse(tmp_path, monkeypatch):
    client, database_path = _owner_client(tmp_path, monkeypatch)
    device_id, _ = _paired_device(client)
    key = "launch-idempotent-0001"
    scheduled_at = datetime.now(UTC).isoformat()
    first = _submit(client, device_id, app="calculator", key=key, scheduled_at=scheduled_at)
    replay = _submit(client, device_id, app="calculator", key=key, scheduled_at=scheduled_at)
    conflict = _submit(client, device_id, app="notepad", key=key, scheduled_at=scheduled_at)
    other_device, _ = _paired_device(client)
    cross_device_reuse = _submit(
        client,
        other_device,
        app="calculator",
        key=key,
        scheduled_at=scheduled_at,
    )
    assert first.status_code == 201
    assert replay.status_code == 200
    assert replay.json()["task"]["task_id"] == first.json()["task"]["task_id"]
    assert conflict.status_code == 409
    assert cross_device_reuse.status_code == 409

    with sqlite3.connect(database_path) as db:
        stored = db.execute(
            "SELECT idempotency_key_hash FROM personal_device_tasks WHERE task_id=?",
            (first.json()["task"]["task_id"],),
        ).fetchone()[0]
        columns = {row[1] for row in db.execute("PRAGMA table_info(personal_device_tasks)")}
    assert len(stored) == 64
    assert key not in stored
    assert "idempotency_key" not in columns
    get_settings.cache_clear()


def test_idempotency_replays_default_and_elapsed_schedule_requests(tmp_path, monkeypatch):
    client, _ = _owner_client(tmp_path, monkeypatch)
    device_id, _ = _paired_device(client)
    fixed_now = datetime(2026, 11, 20, 12, 30, tzinfo=UTC)
    monkeypatch.setattr(DeviceTaskRepository, "_now", staticmethod(lambda: fixed_now))

    default_first = _submit(
        client,
        device_id,
        app="notepad",
        key="idempotency-default-time-001",
    )
    explicit_first = _submit(
        client,
        device_id,
        app="calculator",
        key="idempotency-explicit-time-001",
        scheduled_at=fixed_now.isoformat(),
    )
    assert default_first.status_code == 201
    assert explicit_first.status_code == 201

    later_now = fixed_now + timedelta(minutes=2)
    monkeypatch.setattr(DeviceTaskRepository, "_now", staticmethod(lambda: later_now))
    default_replay = _submit(
        client,
        device_id,
        app="notepad",
        key="idempotency-default-time-001",
    )
    explicit_replay = _submit(
        client,
        device_id,
        app="calculator",
        key="idempotency-explicit-time-001",
        scheduled_at=fixed_now.isoformat(),
    )

    assert default_replay.status_code == 200
    assert explicit_replay.status_code == 200
    assert default_replay.json()["task"]["task_id"] == default_first.json()["task"]["task_id"]
    assert explicit_replay.json()["task"]["task_id"] == explicit_first.json()["task"]["task_id"]
    get_settings.cache_clear()


def test_device_scope_and_owner_boundaries_are_enforced(tmp_path, monkeypatch):
    client, database_path = _owner_client(tmp_path, monkeypatch)
    device_id, device_headers = _paired_device(client, scopes=["device.heartbeat"])
    denied = _submit(client, device_id, app="notepad", key="no-action-scope-001")
    assert denied.status_code == 403
    assert client.post("/devices/tasks/claim", headers=device_headers).json()["task"] is None

    repository = DeviceTaskRepository(database_path)
    with pytest.raises(DeviceTaskNotFound):
        repository.create(
            owner_user_id="another-owner",
            device_id=device_id,
            action="app.launch",
            app="notepad",
            required_scope="app.launch",
            idempotency_key="another-owner-key-001",
            owner_confirmed=False,
            scheduled_at=datetime.now(UTC),
            expires_in_seconds=300,
            timeout_seconds=30,
        )
    get_settings.cache_clear()


def test_arbitrary_actions_and_unbounded_parameters_are_rejected(tmp_path, monkeypatch):
    client, _ = _owner_client(tmp_path, monkeypatch)
    device_id, _ = _paired_device(client)
    invalid_action = _submit(
        client,
        device_id,
        action="shell.execute",
        app=None,
        key="shell-execute-0001",
        command="whoami",
    )
    invalid_app = _submit(
        client,
        device_id,
        app="powershell",
        key="unapproved-app-0001",
    )
    extra = _submit(
        client,
        device_id,
        action="screen.capture",
        app=None,
        key="extra-field-000001",
        screenshot_destination="https://example.invalid",
        confirm_sensitive_action=True,
    )
    assert invalid_action.status_code == 422
    assert invalid_app.status_code == 422
    assert extra.status_code == 422
    get_settings.cache_clear()


def test_screen_capture_requires_explicit_confirmation_and_scope(tmp_path, monkeypatch):
    client, _ = _owner_client(tmp_path, monkeypatch)
    device_id, _ = _paired_device(client)
    unconfirmed = _submit(
        client,
        device_id,
        action="screen.capture",
        app=None,
        key="screen-capture-00001",
    )
    confirmed = _submit(
        client,
        device_id,
        action="screen.capture",
        app=None,
        key="screen-capture-00002",
        confirm_sensitive_action=True,
    )
    assert unconfirmed.status_code == 422
    assert confirmed.status_code == 201
    assert confirmed.json()["task"]["required_scope"] == "screen.capture"
    assert confirmed.json()["task"]["owner_confirmed"] is True
    delayed = _submit(
        client,
        device_id,
        action="screen.capture",
        app=None,
        key="screen-capture-delayed-001",
        confirm_sensitive_action=True,
        scheduled_at=(datetime.now(UTC) + timedelta(minutes=6)).isoformat(),
    )
    assert delayed.status_code == 422
    get_settings.cache_clear()


def test_outcome_requires_the_claim_lease_and_remains_unverified(tmp_path, monkeypatch):
    client, database_path = _owner_client(tmp_path, monkeypatch)
    device_id, device_headers = _paired_device(client)
    submitted = _submit(client, device_id, app="calculator", key="launch-result-000001")
    task_id = submitted.json()["task"]["task_id"]
    claimed = client.post("/devices/tasks/claim", headers=device_headers).json()
    with sqlite3.connect(database_path) as db:
        stored_lease_hash = db.execute(
            "SELECT lease_token_hash FROM personal_device_tasks WHERE task_id=?",
            (task_id,),
        ).fetchone()[0]
    assert stored_lease_hash == hashlib.sha256(claimed["lease_token"].encode()).hexdigest()
    assert claimed["lease_token"] not in stored_lease_hash

    rejected = client.post(
        f"/devices/tasks/{task_id}/complete",
        headers=device_headers,
        json={
            "lease_token": "incorrect-lease-token-value-000000000000",
            "outcome": "succeeded",
        },
    )
    accepted = client.post(
        f"/devices/tasks/{task_id}/complete",
        headers=device_headers,
        json={
            "lease_token": claimed["lease_token"],
            "outcome": "succeeded",
            "duration_ms": 250,
        },
    )
    duplicate = client.post(
        f"/devices/tasks/{task_id}/complete",
        headers=device_headers,
        json={
            "lease_token": claimed["lease_token"],
            "outcome": "succeeded",
            "duration_ms": 250,
        },
    )
    owner_view = client.get(f"/devices/{device_id}/tasks/{task_id}")
    assert rejected.status_code == 409
    assert accepted.status_code == 200
    assert accepted.json()["task"]["status"] == "reported_succeeded"
    assert accepted.json()["task"]["outcome_verified"] is False
    assert duplicate.status_code == 409
    assert owner_view.json()["task"]["status"] == "reported_succeeded"
    with sqlite3.connect(database_path) as db:
        audit_rows = db.execute(
            "SELECT event_type,metadata_json FROM audit_events WHERE subject_id=?",
            (task_id,),
        ).fetchall()
    event_types = {row[0] for row in audit_rows}
    audit_metadata = " ".join(row[1] for row in audit_rows)
    assert {
        "device.task_submitted",
        "device.task_claimed",
        "device.task_outcome_reported",
    }.issubset(event_types)
    assert claimed["lease_token"] not in audit_metadata
    assert "launch-result-000001" not in audit_metadata
    get_settings.cache_clear()


def test_expired_claim_becomes_unknown_outcome_and_is_never_replayed(tmp_path, monkeypatch):
    client, database_path = _owner_client(tmp_path, monkeypatch)
    device_id, device_headers = _paired_device(client)
    submitted = _submit(client, device_id, app="notepad", key="launch-expiry-000001")
    task_id = submitted.json()["task"]["task_id"]
    claimed = client.post("/devices/tasks/claim", headers=device_headers).json()
    with sqlite3.connect(database_path) as db:
        db.execute(
            "UPDATE personal_device_tasks SET lease_expires_at=? WHERE task_id=?",
            ("2000-01-01T00:00:00+00:00", task_id),
        )
    late = client.post(
        f"/devices/tasks/{task_id}/complete",
        headers=device_headers,
        json={"lease_token": claimed["lease_token"], "outcome": "succeeded"},
    )
    owner_view = client.get(f"/devices/{device_id}/tasks/{task_id}")
    assert late.status_code == 409
    assert owner_view.json()["task"]["status"] == "unknown_outcome"
    with sqlite3.connect(database_path) as db:
        completed_at = db.execute(
            "SELECT completed_at FROM personal_device_tasks WHERE task_id=?",
            (task_id,),
        ).fetchone()[0]
    assert completed_at is not None
    assert client.post("/devices/tasks/claim", headers=device_headers).json()["task"] is None
    get_settings.cache_clear()


def test_owner_can_cancel_queued_task_but_not_claimed_task(tmp_path, monkeypatch):
    client, _ = _owner_client(tmp_path, monkeypatch)
    device_id, device_headers = _paired_device(client)
    queued = _submit(client, device_id, app="notepad", key="launch-cancel-queued-001")
    cancelled = client.delete(f"/devices/{device_id}/tasks/{queued.json()['task']['task_id']}")
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"

    active = _submit(client, device_id, app="calculator", key="launch-cancel-active-001")
    claimed = client.post("/devices/tasks/claim", headers=device_headers).json()
    assert claimed["task"]["task_id"] == active.json()["task"]["task_id"]
    refused = client.delete(f"/devices/{device_id}/tasks/{claimed['task']['task_id']}")
    assert refused.status_code == 409
    get_settings.cache_clear()


def test_device_revocation_cancels_queued_and_fences_claimed_tasks(tmp_path, monkeypatch):
    client, _ = _owner_client(tmp_path, monkeypatch)
    device_id, device_headers = _paired_device(client)
    claimed_task = _submit(client, device_id, app="notepad", key="revoke-claimed-task-001")
    queued_task = _submit(client, device_id, app="calculator", key="revoke-queued-task-001")
    claim = client.post("/devices/tasks/claim", headers=device_headers).json()
    assert claim["task"]["task_id"] == claimed_task.json()["task"]["task_id"]

    revoked = client.delete(f"/devices/{device_id}")
    assert revoked.status_code == 200
    tasks = client.get(f"/devices/{device_id}/tasks").json()["tasks"]
    statuses = {task["task_id"]: task["status"] for task in tasks}
    assert statuses[claimed_task.json()["task"]["task_id"]] == "unknown_outcome"
    assert statuses[queued_task.json()["task"]["task_id"]] == "cancelled"
    assert client.post("/devices/tasks/claim", headers=device_headers).status_code == 401
    get_settings.cache_clear()


def test_device_queue_is_bounded_per_device(tmp_path, monkeypatch):
    client, _ = _owner_client(tmp_path, monkeypatch)
    device_id, _ = _paired_device(client)
    scheduled_at = (datetime.now(UTC) + timedelta(minutes=2)).isoformat()
    for index in range(100):
        response = _submit(
            client,
            device_id,
            app="notepad",
            key=f"queue-limit-{index:04d}",
            scheduled_at=scheduled_at,
        )
        assert response.status_code == 201
    full = _submit(
        client,
        device_id,
        app="notepad",
        key="queue-limit-overflow",
        scheduled_at=scheduled_at,
    )
    assert full.status_code == 409
    get_settings.cache_clear()

def test_schedule_requires_timezone_and_has_a_bounded_horizon(tmp_path, monkeypatch):
    client, _ = _owner_client(tmp_path, monkeypatch)
    device_id, _ = _paired_device(client)
    naive = _submit(
        client,
        device_id,
        app="notepad",
        key="schedule-naive-00001",
        scheduled_at="2026-11-20T12:00:00",
    )
    too_far = _submit(
        client,
        device_id,
        app="notepad",
        key="schedule-too-far-0001",
        scheduled_at=(datetime.now(UTC) + timedelta(days=31)).isoformat(),
    )
    too_long = _submit(
        client,
        device_id,
        app="notepad",
        key="schedule-too-long-001",
        expires_in_seconds=86_401,
    )
    assert naive.status_code == 422
    assert too_far.status_code == 422
    assert too_long.status_code == 422
    get_settings.cache_clear()


def test_tasks_are_isolated_between_two_paired_devices(tmp_path, monkeypatch):
    client, _ = _owner_client(tmp_path, monkeypatch)
    first_device, first_headers = _paired_device(client)
    _second_device, second_headers = _paired_device(client)
    submitted = _submit(
        client,
        first_device,
        app="notepad",
        key="device-isolation-task-001",
    )
    assert submitted.status_code == 201

    wrong_device_claim = client.post("/devices/tasks/claim", headers=second_headers)
    right_device_claim = client.post("/devices/tasks/claim", headers=first_headers)
    assert wrong_device_claim.status_code == 200
    assert wrong_device_claim.json()["task"] is None
    assert right_device_claim.json()["task"]["task_id"] == submitted.json()["task"]["task_id"]
    get_settings.cache_clear()




def test_model_device_task_creation_rechecks_active_owner_grants_atomically(tmp_path, monkeypatch):
    client, database_path = _owner_client(tmp_path, monkeypatch)
    device_id, _ = _paired_device(client)

    for permission in ("device.registry.read", "device.app_launch"):
        granted = client.put(
            f"/tools/grants/{permission}",
            json={"expires_in_seconds": 600},
        )
        assert granted.status_code == 200

    repository = DeviceTaskRepository(database_path)
    required = frozenset({"device.registry.read", "device.app_launch"})
    with sqlite3.connect(database_path) as db:
        owner_user_id = db.execute("SELECT user_id FROM auth_users LIMIT 1").fetchone()[0]
    common = {
        "owner_user_id": owner_user_id,
        "device_id": device_id,
        "action": "app.launch",
        "app": "notepad",
        "required_scope": "app.launch",
        "owner_confirmed": False,
        "scheduled_at": datetime.now(UTC),
        "expires_in_seconds": 300,
        "timeout_seconds": 30,
        "required_owner_permissions": required,
    }

    allowed, created = repository.create(
        **common,
        idempotency_key="owner-grant-atomic-allow-001",
    )
    assert created is True
    assert allowed["status"] == "queued"

    revoked = client.delete("/tools/grants/device.app_launch")
    assert revoked.status_code == 204
    with pytest.raises(DeviceTaskPermissionError) as denied:
        repository.create(
            **common,
            idempotency_key="owner-grant-atomic-deny-001",
        )
    assert "active grant" in str(denied.value).lower()
    with sqlite3.connect(database_path) as db:
        count = db.execute(
            "SELECT COUNT(*) FROM personal_device_tasks WHERE idempotency_key_hash=?",
            (hashlib.sha256(b"owner-grant-atomic-deny-001").hexdigest(),),
        ).fetchone()[0]
    assert count == 0
    get_settings.cache_clear()


def test_model_device_task_creation_uses_time_after_write_lock_for_grants(tmp_path, monkeypatch):
    client, database_path = _owner_client(tmp_path, monkeypatch)
    device_id, _ = _paired_device(client)

    for permission in ("device.registry.read", "device.app_launch"):
        granted = client.put(
            f"/tools/grants/{permission}",
            json={"expires_in_seconds": 600},
        )
        assert granted.status_code == 200

    before_lock = datetime(2026, 11, 21, 12, 0, tzinfo=UTC)
    after_lock = before_lock + timedelta(seconds=10)
    expires_at = (before_lock + timedelta(seconds=5)).isoformat()
    with sqlite3.connect(database_path) as db:
        owner_user_id = db.execute("SELECT user_id FROM auth_users LIMIT 1").fetchone()[0]
        db.execute(
            "UPDATE tool_permission_grants SET expires_at=? WHERE owner_user_id=?",
            (expires_at, owner_user_id),
        )
        db.commit()

    times = iter((before_lock, after_lock))
    monkeypatch.setattr(DeviceTaskRepository, "_now", staticmethod(lambda: next(times)))
    repository = DeviceTaskRepository(database_path)
    with pytest.raises(DeviceTaskPermissionError):
        repository.create(
            owner_user_id=owner_user_id,
            device_id=device_id,
            action="app.launch",
            app="notepad",
            required_scope="app.launch",
            idempotency_key="owner-grant-expiry-after-lock-001",
            owner_confirmed=False,
            scheduled_at=before_lock,
            expires_in_seconds=300,
            timeout_seconds=30,
            required_owner_permissions=frozenset({
                "device.registry.read",
                "device.app_launch",
            }),
        )

    with sqlite3.connect(database_path) as db:
        count = db.execute(
            "SELECT COUNT(*) FROM personal_device_tasks WHERE idempotency_key_hash=?",
            (hashlib.sha256(b"owner-grant-expiry-after-lock-001").hexdigest(),),
        ).fetchone()[0]
    assert count == 0
    get_settings.cache_clear()
