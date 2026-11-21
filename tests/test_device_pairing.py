import hashlib
import sqlite3
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from mrhub.config import get_settings
from mrhub.devices.pairing import DevicePairingError, DevicePairingRepository
from mrhub.main import create_app


def _owner_client(tmp_path, monkeypatch):
    database_path = tmp_path / "device-pairing.sqlite3"
    monkeypatch.setenv("MRH_DATABASE_PATH", str(database_path))
    get_settings.cache_clear()
    client = TestClient(create_app())
    password = "test-only-strong-password-2026"
    assert client.post("/auth/setup", json={"password": password}).status_code == 201
    login = client.post("/auth/login", json={"username": "owner", "password": password})
    assert login.status_code == 200
    client.headers.update({"Authorization": f"Bearer {login.json()['access_token']}"})
    return client, database_path


def _create_challenge(client, scopes=None):
    payload = {
        "device_id": str(uuid4()),
        "platform": "windows",
        "label": "Siavash Windows workstation",
        "advertised_capabilities": ["device.heartbeat", "screen.capture", "app.launch"],
    }
    if scopes is not None:
        payload["scopes"] = scopes
    response = client.post("/devices/pairing-challenges", json=payload)
    assert response.status_code == 201
    return payload, response.json()


def _exchange(client, payload, challenge, *, device_id=None):
    return client.post("/devices/pair", json={
        "pairing_code": challenge["pairing_code"],
        "device_id": payload["device_id"] if device_id is None else device_id,
        "agent_version": "0.1.0",
        "os_version": "Windows 11",
    })


def _device_headers(tokens, device_id):
    return {
        "Authorization": f"Bearer {tokens['access_token']}",
        "X-Device-ID": device_id,
    }


class _ClockAdvancingConnection:
    def __init__(
        self,
        connection: sqlite3.Connection,
        clock: dict[str, datetime],
        after: datetime,
    ) -> None:
        self._connection = connection
        self._clock = clock
        self._after = after

    def execute(self, sql: str, parameters: tuple[object, ...] = ()) -> sqlite3.Cursor:
        cursor = self._connection.execute(sql, parameters)
        if sql.strip().upper() == "BEGIN IMMEDIATE":
            self._clock["now"] = self._after
        return cursor

    def __getattr__(self, name: str):
        return getattr(self._connection, name)


def _advance_clock_after_write_lock(
    repository: DevicePairingRepository,
    monkeypatch,
    *,
    before: datetime,
    after: datetime,
) -> None:
    clock = {"now": before}
    monkeypatch.setattr(DevicePairingRepository, "_now", staticmethod(lambda: clock["now"]))
    original_connect = repository._connect
    monkeypatch.setattr(
        repository,
        "_connect",
        lambda: _ClockAdvancingConnection(original_connect(), clock, after),
    )


def test_device_pairing_is_owner_initiated_and_stores_only_hashes(tmp_path, monkeypatch):
    client, database_path = _owner_client(tmp_path, monkeypatch)
    payload, challenge = _create_challenge(client, scopes=["device.heartbeat", "screen.capture"])
    exchanged = _exchange(client, payload, challenge)
    assert exchanged.status_code == 200
    tokens = exchanged.json()
    assert tokens["expires_in"] == 900
    assert tokens["refresh_expires_in"] == 30 * 24 * 60 * 60
    assert tokens["scopes"] == ["device.heartbeat", "screen.capture"]

    with sqlite3.connect(database_path) as db:
        token_hashes = {row[0] for row in db.execute("SELECT token_hash FROM personal_device_tokens")}
        challenge_hashes = {row[0] for row in db.execute("SELECT challenge_hash FROM personal_device_pairing_challenges")}
    assert hashlib.sha256(tokens["access_token"].encode()).hexdigest() in token_hashes
    assert tokens["access_token"] not in token_hashes
    assert hashlib.sha256(challenge["pairing_code"].encode()).hexdigest() in challenge_hashes
    assert challenge["pairing_code"] not in challenge_hashes
    get_settings.cache_clear()


def test_pairing_code_is_single_use_and_bound_to_device_id(tmp_path, monkeypatch):
    client, _ = _owner_client(tmp_path, monkeypatch)
    payload, challenge = _create_challenge(client)
    assert _exchange(client, payload, challenge, device_id=str(uuid4())).status_code == 401
    assert _exchange(client, payload, challenge).status_code == 200
    assert _exchange(client, payload, challenge).status_code == 401
    get_settings.cache_clear()


def test_device_heartbeat_requires_scope_and_owner_can_revoke(tmp_path, monkeypatch):
    client, _ = _owner_client(tmp_path, monkeypatch)
    payload, challenge = _create_challenge(client, scopes=["device.heartbeat"])
    tokens = _exchange(client, payload, challenge).json()
    headers = _device_headers(tokens, payload["device_id"])
    heartbeat = client.post("/devices/heartbeat", headers=headers, json={
        "agent_version": "0.1.1", "runtime_state": "busy", "app_uptime_seconds": 60,
        "last_task_id": "a4e1b9cc-cb55-4c2d-aed0-c8e1ec9c40f4",
    })
    assert heartbeat.status_code == 200
    assert heartbeat.json()["runtime_state"] == "busy"
    assert heartbeat.json()["app_uptime_seconds"] == 60
    assert heartbeat.json()["last_task_id"] == "a4e1b9cc-cb55-4c2d-aed0-c8e1ec9c40f4"
    device = client.get("/devices").json()["devices"][0]
    assert device["last_seen_at"] is not None
    assert device["runtime_state"] == "busy"
    assert device["app_uptime_seconds"] == 60
    assert device["last_task_id"] == "a4e1b9cc-cb55-4c2d-aed0-c8e1ec9c40f4"

    denied = client.post("/devices/heartbeat", headers={
        **headers, "X-Device-ID": str(uuid4())
    }, json={"agent_version": "0.1.1", "runtime_state": "ready", "app_uptime_seconds": 60})
    assert denied.status_code == 401

    revoked = client.delete(f"/devices/{payload['device_id']}")
    assert revoked.status_code == 200
    assert client.post("/devices/heartbeat", headers=headers, json={
        "agent_version": "0.1.1", "runtime_state": "ready", "app_uptime_seconds": 60,
    }).status_code == 401
    assert client.get("/devices").json()["devices"][0]["status"] == "revoked"
    get_settings.cache_clear()


def test_device_refresh_rotates_credentials_and_revokes_device_on_replay(tmp_path, monkeypatch):
    client, database_path = _owner_client(tmp_path, monkeypatch)
    payload, challenge = _create_challenge(client, scopes=["device.heartbeat", "app.launch"])
    tokens = _exchange(client, payload, challenge).json()
    body = {"refresh_token": tokens["refresh_token"], "device_id": payload["device_id"]}

    wrong_device = client.post(
        "/devices/refresh",
        json={"refresh_token": tokens["refresh_token"], "device_id": str(uuid4())},
    )
    assert wrong_device.status_code == 401

    claimed_submission = client.post(
        f"/devices/{payload['device_id']}/tasks",
        headers={"Idempotency-Key": "refresh-replay-claimed-001"},
        json={"action": "app.launch", "app": "notepad"},
    )
    assert claimed_submission.status_code == 201
    claimed = client.post(
        "/devices/tasks/claim",
        headers=_device_headers(tokens, payload["device_id"]),
    )
    claimed_task_id = claimed.json()["task"]["task_id"]
    assert claimed_task_id == claimed_submission.json()["task"]["task_id"]

    queued_submission = client.post(
        f"/devices/{payload['device_id']}/tasks",
        headers={"Idempotency-Key": "refresh-replay-queued-001"},
        json={"action": "app.launch", "app": "calculator"},
    )
    assert queued_submission.status_code == 201
    queued_task_id = queued_submission.json()["task"]["task_id"]

    refreshed = client.post("/devices/refresh", json=body)
    assert refreshed.status_code == 200
    assert refreshed.json()["access_token"] != tokens["access_token"]

    replay = client.post("/devices/refresh", json=body)
    assert replay.status_code == 401
    device = client.get("/devices").json()["devices"][0]
    assert device["status"] == "revoked"
    task_rows = client.get(f"/devices/{payload['device_id']}/tasks").json()["tasks"]
    task_statuses = {item["task_id"]: item["status"] for item in task_rows}
    assert task_statuses[claimed_task_id] == "unknown_outcome"
    assert task_statuses[queued_task_id] == "cancelled"

    heartbeat = client.post(
        "/devices/heartbeat",
        headers=_device_headers(refreshed.json(), payload["device_id"]),
        json={"agent_version": "0.1.0", "runtime_state": "ready", "app_uptime_seconds": 0},
    )
    assert heartbeat.status_code == 401

    with sqlite3.connect(database_path) as db:
        active_tokens = db.execute(
            "SELECT COUNT(*) FROM personal_device_tokens WHERE device_id=? AND revoked_at IS NULL",
            (payload["device_id"],),
        ).fetchone()[0]
        reuse_events = db.execute(
            "SELECT COUNT(*) FROM audit_events WHERE subject_id=? AND event_type='device.refresh_reuse_detected'",
            (payload["device_id"],),
        ).fetchone()[0]
        task_security_events = db.execute(
            """SELECT COUNT(*) FROM audit_events
               WHERE subject_id IN (?,?) AND actor_type='device_security'
                 AND event_type IN ('device.task_cancelled','device.task_unknown_outcome')""",
            (claimed_task_id, queued_task_id),
        ).fetchone()[0]
    assert active_tokens == 0
    assert reuse_events == 1
    assert task_security_events == 2
    get_settings.cache_clear()


def test_device_pairing_rejects_unknown_scopes_and_unexpected_fields(tmp_path, monkeypatch):
    client, _ = _owner_client(tmp_path, monkeypatch)
    bad_scope = client.post("/devices/pairing-challenges", json={
        "device_id": str(uuid4()), "platform": "windows", "label": "PC",
        "scopes": ["shell.execute"],
    })
    assert bad_scope.status_code == 422
    bad_field = client.post("/devices/pairing-challenges", json={
        "device_id": str(uuid4()), "platform": "windows", "label": "PC",
        "arbitrary_command": "whoami",
    })
    assert bad_field.status_code == 422
    get_settings.cache_clear()

def test_expired_pairing_challenge_can_be_reissued_for_same_unpaired_device(tmp_path, monkeypatch):
    client, database_path = _owner_client(tmp_path, monkeypatch)
    payload, _challenge = _create_challenge(client)
    with sqlite3.connect(database_path) as db:
        db.execute(
            "UPDATE personal_device_pairing_challenges SET expires_at=? WHERE device_id=?",
            ("2000-01-01T00:00:00+00:00", payload["device_id"]),
        )
    replacement = client.post("/devices/pairing-challenges", json=payload)
    assert replacement.status_code == 201
    assert replacement.json()["device_id"] == payload["device_id"]
    get_settings.cache_clear()

def test_pairing_challenge_registry_is_bounded_and_prunes_expired_rows(tmp_path, monkeypatch):
    client, database_path = _owner_client(tmp_path, monkeypatch)
    pending = [_create_challenge(client) for _ in range(10)]

    overflow_payload = {
        "device_id": str(uuid4()),
        "platform": "windows",
        "label": "Overflow device",
        "advertised_capabilities": ["device.heartbeat"],
    }
    overflow = client.post("/devices/pairing-challenges", json=overflow_payload)
    assert overflow.status_code == 422
    assert "too many pending" in overflow.json()["detail"].lower()

    expired_device_id = pending[0][0]["device_id"]
    with sqlite3.connect(database_path) as db:
        db.execute(
            "UPDATE personal_device_pairing_challenges SET expires_at=? WHERE device_id=?",
            ("2000-01-01T00:00:00+00:00", expired_device_id),
        )

    replacement = client.post("/devices/pairing-challenges", json=overflow_payload)
    assert replacement.status_code == 201
    with sqlite3.connect(database_path) as db:
        stale = db.execute(
            "SELECT 1 FROM personal_device_pairing_challenges WHERE device_id=?",
            (expired_device_id,),
        ).fetchone()
        active_count = db.execute(
            """SELECT COUNT(*) FROM personal_device_pairing_challenges
               WHERE consumed_at IS NULL AND expires_at>?""",
            ("2000-01-01T00:00:00+00:00",),
        ).fetchone()[0]
    assert stale is None
    assert active_count == 10
    get_settings.cache_clear()


def test_pairing_requires_heartbeat_scope(tmp_path, monkeypatch):
    client, _ = _owner_client(tmp_path, monkeypatch)
    challenge = client.post("/devices/pairing-challenges", json={
        "device_id": str(uuid4()),
        "platform": "windows",
        "label": "PC",
        "advertised_capabilities": ["app.launch"],
        "scopes": ["app.launch"],
    })
    assert challenge.status_code == 422
    assert "device.heartbeat" in challenge.json()["detail"]
    get_settings.cache_clear()



def test_pairing_challenge_ttl_starts_after_write_lock(tmp_path, monkeypatch):
    client, database_path = _owner_client(tmp_path, monkeypatch)
    assert client.get("/devices").status_code == 200
    with sqlite3.connect(database_path) as db:
        owner_user_id = db.execute("SELECT user_id FROM auth_users LIMIT 1").fetchone()[0]

    repository = DevicePairingRepository(database_path)
    before = datetime.now(UTC)
    after = before + timedelta(minutes=2)
    _advance_clock_after_write_lock(repository, monkeypatch, before=before, after=after)
    device_id = str(uuid4())
    code, expires_at = repository.create_challenge(
        owner_user_id=owner_user_id,
        device_id=device_id,
        platform="windows",
        label="Lock-delayed workstation",
        advertised_capabilities=("device.heartbeat",),
        scopes=frozenset({"device.heartbeat"}),
    )

    assert expires_at == after + timedelta(seconds=repository.CHALLENGE_TTL_SECONDS)
    with sqlite3.connect(database_path) as db:
        row = db.execute(
            "SELECT created_at,expires_at FROM personal_device_pairing_challenges "
            "WHERE challenge_hash=?",
            (hashlib.sha256(code.encode()).hexdigest(),),
        ).fetchone()
    assert row == (after.isoformat(), expires_at.isoformat())
    get_settings.cache_clear()


def test_pairing_exchange_rejects_challenge_expired_during_write_lock(tmp_path, monkeypatch):
    client, database_path = _owner_client(tmp_path, monkeypatch)
    payload, challenge = _create_challenge(client)
    before = datetime.now(UTC)
    after = before + timedelta(seconds=10)
    with sqlite3.connect(database_path) as db:
        db.execute(
            "UPDATE personal_device_pairing_challenges SET expires_at=? WHERE device_id=?",
            ((before + timedelta(seconds=5)).isoformat(), payload["device_id"]),
        )

    repository = DevicePairingRepository(database_path)
    _advance_clock_after_write_lock(repository, monkeypatch, before=before, after=after)
    with pytest.raises(DevicePairingError):
        repository.exchange(
            pairing_code=challenge["pairing_code"],
            device_id=payload["device_id"],
            agent_version="0.1.0",
            os_version="Windows 11",
        )

    with sqlite3.connect(database_path) as db:
        consumed_at = db.execute(
            "SELECT consumed_at FROM personal_device_pairing_challenges WHERE device_id=?",
            (payload["device_id"],),
        ).fetchone()[0]
        device_count = db.execute(
            "SELECT COUNT(*) FROM personal_devices WHERE device_id=?",
            (payload["device_id"],),
        ).fetchone()[0]
    assert consumed_at is None
    assert device_count == 0
    get_settings.cache_clear()


def test_pairing_exchange_token_ttls_start_after_write_lock(tmp_path, monkeypatch):
    client, database_path = _owner_client(tmp_path, monkeypatch)
    payload, challenge = _create_challenge(client)
    before = datetime.now(UTC)
    after = before + timedelta(seconds=10)
    repository = DevicePairingRepository(database_path)
    _advance_clock_after_write_lock(repository, monkeypatch, before=before, after=after)

    tokens = repository.exchange(
        pairing_code=challenge["pairing_code"],
        device_id=payload["device_id"],
        agent_version="0.1.0",
        os_version="Windows 11",
    )
    with sqlite3.connect(database_path) as db:
        rows = {
            row[0]: (row[1], row[2])
            for row in db.execute(
                "SELECT token_type,created_at,expires_at FROM personal_device_tokens "
                "WHERE device_id=?",
                (payload["device_id"],),
            )
        }
    assert rows["access"] == (
        after.isoformat(),
        (after + timedelta(seconds=repository.ACCESS_TTL_SECONDS)).isoformat(),
    )
    assert rows["refresh"] == (
        after.isoformat(),
        (after + timedelta(seconds=repository.REFRESH_TTL_SECONDS)).isoformat(),
    )
    assert tokens["device_id"] == payload["device_id"]
    get_settings.cache_clear()


def test_refresh_rejects_credential_expired_during_write_lock(tmp_path, monkeypatch):
    client, database_path = _owner_client(tmp_path, monkeypatch)
    payload, challenge = _create_challenge(client)
    tokens = _exchange(client, payload, challenge).json()
    before = datetime.now(UTC)
    after = before + timedelta(seconds=10)
    token_hash = hashlib.sha256(tokens["refresh_token"].encode()).hexdigest()
    with sqlite3.connect(database_path) as db:
        db.execute(
            "UPDATE personal_device_tokens SET expires_at=? WHERE token_hash=?",
            ((before + timedelta(seconds=5)).isoformat(), token_hash),
        )

    repository = DevicePairingRepository(database_path)
    _advance_clock_after_write_lock(repository, monkeypatch, before=before, after=after)
    with pytest.raises(DevicePairingError):
        repository.refresh(
            refresh_token=tokens["refresh_token"],
            device_id=payload["device_id"],
        )

    with sqlite3.connect(database_path) as db:
        token = db.execute(
            "SELECT revoked_at FROM personal_device_tokens WHERE token_hash=?",
            (token_hash,),
        ).fetchone()
        token_count = db.execute(
            "SELECT COUNT(*) FROM personal_device_tokens WHERE device_id=?",
            (payload["device_id"],),
        ).fetchone()[0]
    assert token[0] is None
    assert token_count == 2
    get_settings.cache_clear()
