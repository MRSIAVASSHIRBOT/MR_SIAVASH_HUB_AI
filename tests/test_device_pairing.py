import hashlib
import sqlite3
from uuid import uuid4

from fastapi.testclient import TestClient

from mrhub.config import get_settings
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
    assert hashlib.sha256(tokens["refresh_token"].encode()).hexdigest() in token_hashes
    assert tokens["refresh_token"] not in token_hashes
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
        "agent_version": "0.1.1", "runtime_state": "ready", "app_uptime_seconds": 60,
    })
    assert heartbeat.status_code == 200
    assert client.get("/devices").json()["devices"][0]["last_seen_at"] is not None

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


def test_device_refresh_rotates_credentials_and_rejects_replay(tmp_path, monkeypatch):
    client, _ = _owner_client(tmp_path, monkeypatch)
    payload, challenge = _create_challenge(client)
    tokens = _exchange(client, payload, challenge).json()
    body = {"refresh_token": tokens["refresh_token"], "device_id": payload["device_id"]}
    refreshed = client.post("/devices/refresh", json=body)
    assert refreshed.status_code == 200
    assert refreshed.json()["access_token"] != tokens["access_token"]
    assert client.post("/devices/refresh", json=body).status_code == 401
    with sqlite3.connect(database_path) as db:
        hashes = {row[0] for row in db.execute("SELECT token_hash FROM personal_device_tokens")}
    assert hashlib.sha256(tokens["refresh_token"].encode()).hexdigest() in hashes
    assert tokens["refresh_token"] not in hashes
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


def test_pairing_exchange_rejects_control_characters_in_os_version(tmp_path, monkeypatch):
    client, _ = _owner_client(tmp_path, monkeypatch)
    payload, challenge = _create_challenge(client)
    invalid = client.post("/devices/pair", json={
        "pairing_code": challenge["pairing_code"],
        "device_id": payload["device_id"],
        "agent_version": "0.1.0",
        "os_version": "Windows 11\\nInjected",
    })
    assert invalid.status_code == 422
    assert _exchange(client, payload, challenge).status_code == 200
    get_settings.cache_clear()


def test_device_registry_listing_and_revocation_are_owner_scoped(tmp_path, monkeypatch):
    client, database_path = _owner_client(tmp_path, monkeypatch)
    payload, challenge = _create_challenge(client)
    tokens = _exchange(client, payload, challenge).json()
    with sqlite3.connect(database_path) as db:
        owner_user_id = db.execute(
            "SELECT user_id FROM auth_users WHERE username='owner'"
        ).fetchone()[0]

    from mrhub.devices.pairing import DevicePairingRepository

    repository = DevicePairingRepository(database_path)
    assert len(repository.list_devices(owner_user_id)) == 1
    assert repository.list_devices("different-owner") == []
    assert repository.revoke(
        owner_user_id="different-owner", device_id=payload["device_id"]
    ) is False
    assert repository.authenticate(
        access_token=tokens["access_token"], device_id=payload["device_id"]
    ) is not None
    assert repository.revoke(
        owner_user_id=owner_user_id, device_id=payload["device_id"]
    ) is True
    assert repository.authenticate(
        access_token=tokens["access_token"], device_id=payload["device_id"]
    ) is None
    get_settings.cache_clear()
