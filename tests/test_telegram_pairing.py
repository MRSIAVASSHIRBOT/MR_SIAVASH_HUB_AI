import hashlib
import sqlite3
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from mrhub.config import get_settings
from mrhub.domain.tasks import TaskStatus
from mrhub.infrastructure.database import TaskRepository
from mrhub.jobs.engine import JobEngine
from mrhub.main import create_app
from mrhub.memory.repository import MemoryRepository


def _owner_client(tmp_path, monkeypatch):
    database_path = tmp_path / "telegram-pairing.sqlite3"
    monkeypatch.setenv("MRH_DATABASE_PATH", str(database_path))
    get_settings.cache_clear()
    client = TestClient(create_app())
    password = "test-only-strong-password-2026"
    assert client.post("/auth/setup", json={"password": password}).status_code == 201
    login = client.post("/auth/login", json={"username": "owner", "password": password})
    assert login.status_code == 200
    client.headers.update({"Authorization": f"Bearer {login.json()['access_token']}"})
    return client, database_path


def _create_pairing(client, telegram_user_id=123456789, scopes=None):
    payload = {
        "telegram_user_id": telegram_user_id,
        "client_id": str(uuid4()),
        "label": "MR_SIAVASH_EL_AI local bot",
    }
    if scopes is not None:
        payload["scopes"] = scopes
    response = client.post("/integrations/telegram/pairing-challenges", json=payload)
    assert response.status_code == 201
    return payload, response.json()


def _exchange(client, payload, challenge, telegram_user_id=None):
    return client.post(
        "/integrations/telegram/exchange",
        json={
            "pairing_code": challenge["pairing_code"],
            "telegram_user_id": (
                payload["telegram_user_id"] if telegram_user_id is None else telegram_user_id
            ),
            "client_id": payload["client_id"],
        },
    )


def _bot_headers(tokens, telegram_user_id=123456789):
    return {
        "Authorization": f"Bearer {tokens['access_token']}",
        "X-Telegram-User-Id": str(telegram_user_id),
    }


def test_pairing_is_owner_initiated_and_issues_scoped_credentials(tmp_path, monkeypatch):
    client, database_path = _owner_client(tmp_path, monkeypatch)
    payload, challenge = _create_pairing(client)
    assert len(challenge["pairing_code"]) >= 40
    assert challenge["scopes"] == ["status:read"]

    exchanged = _exchange(client, payload, challenge)
    assert exchanged.status_code == 200
    tokens = exchanged.json()
    assert tokens["expires_in"] == 900
    assert tokens["refresh_expires_in"] == 30 * 24 * 60 * 60
    assert tokens["client_id"] == payload["client_id"]

    status = client.get(
        "/integrations/telegram/status",
        headers=_bot_headers(tokens),
    )
    assert status.status_code == 200
    assert status.json()["client_id"] == payload["client_id"]
    assert client.get(
        "/integrations/telegram/tasks", headers=_bot_headers(tokens)
    ).status_code == 403
    assert client.get(
        f"/integrations/telegram/tasks/{uuid4()}", headers=_bot_headers(tokens)
    ).status_code == 403
    assert client.post(
        "/integrations/telegram/memory/search",
        json={"query": "private"},
        headers=_bot_headers(tokens),
    ).status_code == 403

    with sqlite3.connect(database_path) as connection:
        stored_hashes = {
            row[0]
            for row in connection.execute(
                "SELECT token_hash FROM telegram_access_tokens"
            ).fetchall()
        }
        challenge_hashes = {
            row[0]
            for row in connection.execute(
                "SELECT challenge_hash FROM telegram_pairing_challenges"
            ).fetchall()
        }
    assert hashlib.sha256(tokens["access_token"].encode()).hexdigest() in stored_hashes
    assert tokens["access_token"] not in stored_hashes
    assert hashlib.sha256(challenge["pairing_code"].encode()).hexdigest() in challenge_hashes
    assert challenge["pairing_code"] not in challenge_hashes
    get_settings.cache_clear()


def test_pairing_challenge_cannot_be_used_by_another_telegram_user(tmp_path, monkeypatch):
    client, _ = _owner_client(tmp_path, monkeypatch)
    payload, challenge = _create_pairing(client)
    wrong_user = _exchange(client, payload, challenge, telegram_user_id=987654321)
    assert wrong_user.status_code == 401

    valid = _exchange(client, payload, challenge)
    assert valid.status_code == 200
    get_settings.cache_clear()


def test_pairing_code_is_single_use_and_bound_to_client_id(tmp_path, monkeypatch):
    client, _ = _owner_client(tmp_path, monkeypatch)
    payload, challenge = _create_pairing(client)

    wrong_client = client.post(
        "/integrations/telegram/exchange",
        json={
            "pairing_code": challenge["pairing_code"],
            "telegram_user_id": payload["telegram_user_id"],
            "client_id": str(uuid4()),
        },
    )
    assert wrong_client.status_code == 401
    assert _exchange(client, payload, challenge).status_code == 200
    assert _exchange(client, payload, challenge).status_code == 401
    get_settings.cache_clear()


def test_pairing_challenge_expiry_is_enforced(tmp_path, monkeypatch):
    client, database_path = _owner_client(tmp_path, monkeypatch)
    payload, challenge = _create_pairing(client)
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            "UPDATE telegram_pairing_challenges SET expires_at = ?",
            ("2000-01-01T00:00:00+00:00",),
        )
    assert _exchange(client, payload, challenge).status_code == 401
    get_settings.cache_clear()


def test_telegram_scope_limits_tasks_and_memory_capabilities(tmp_path, monkeypatch):
    client, _ = _owner_client(tmp_path, monkeypatch)
    payload, challenge = _create_pairing(client, scopes=["status:read"])
    tokens = _exchange(client, payload, challenge).json()

    assert client.get(
        "/integrations/telegram/status", headers=_bot_headers(tokens)
    ).status_code == 200
    assert client.get(
        "/integrations/telegram/tasks", headers=_bot_headers(tokens)
    ).status_code == 403
    assert client.post(
        "/integrations/telegram/memory/search",
        json={"query": "test"},
        headers=_bot_headers(tokens),
    ).status_code == 403
    get_settings.cache_clear()


def test_telegram_task_creation_is_idempotent_and_policy_checked(tmp_path, monkeypatch):
    client, _ = _owner_client(tmp_path, monkeypatch)
    payload, challenge = _create_pairing(client, scopes=["tasks:create", "tasks:read"])
    tokens = _exchange(client, payload, challenge).json()
    headers = {**_bot_headers(tokens), "Idempotency-Key": "telegram-create-task-001"}
    body = {"task_type": "demo.echo", "description": "safe test task"}

    first = client.post("/integrations/telegram/tasks", json=body, headers=headers)
    replay = client.post("/integrations/telegram/tasks", json=body, headers=headers)
    assert first.status_code == 201
    assert replay.status_code == 200
    assert replay.json()["task_id"] == first.json()["task_id"]

    high_risk = client.post(
        "/integrations/telegram/tasks",
        json={"task_type": "unregistered.external_action", "description": "needs review"},
        headers={**_bot_headers(tokens), "Idempotency-Key": "telegram-high-risk-002"},
    )
    assert high_risk.status_code == 201
    assert high_risk.json()["status"] == "waiting_approval"
    get_settings.cache_clear()


def test_refresh_credential_is_bound_to_telegram_identity(tmp_path, monkeypatch):
    client, _ = _owner_client(tmp_path, monkeypatch)
    payload, challenge = _create_pairing(client)
    tokens = _exchange(client, payload, challenge).json()

    wrong_user = client.post(
        "/integrations/telegram/refresh",
        json={"refresh_token": tokens["refresh_token"], "telegram_user_id": 999999999},
    )
    assert wrong_user.status_code == 401

    refreshed = client.post(
        "/integrations/telegram/refresh",
        json={"refresh_token": tokens["refresh_token"], "telegram_user_id": 123456789},
    )
    assert refreshed.status_code == 200
    assert refreshed.json()["access_token"] != tokens["access_token"]
    get_settings.cache_clear()


def test_owner_can_revoke_paired_client_and_all_its_tokens(tmp_path, monkeypatch):
    client, _ = _owner_client(tmp_path, monkeypatch)
    payload, challenge = _create_pairing(client)
    tokens = _exchange(client, payload, challenge).json()

    clients = client.get("/integrations/telegram/clients")
    assert clients.status_code == 200
    assert clients.json()["count"] == 1

    revoked = client.post(f"/integrations/telegram/clients/{payload['client_id']}/revoke")
    assert revoked.status_code == 200
    assert revoked.json()["revoked"] is True

    assert client.get(
        "/integrations/telegram/status", headers=_bot_headers(tokens)
    ).status_code == 401
    assert client.post(
        "/integrations/telegram/refresh",
        json={"refresh_token": tokens["refresh_token"], "telegram_user_id": 123456789},
    ).status_code == 401
    get_settings.cache_clear()


def test_pairing_challenge_requires_owner_authentication(tmp_path, monkeypatch):
    monkeypatch.setenv("MRH_DATABASE_PATH", str(tmp_path / "unauthenticated.sqlite3"))
    get_settings.cache_clear()
    client = TestClient(create_app())
    response = client.post(
        "/integrations/telegram/pairing-challenges",
        json={
            "telegram_user_id": 123456789,
            "client_id": str(uuid4()),
            "label": "unauthorized",
        },
    )
    assert response.status_code == 401
    get_settings.cache_clear()



def test_telegram_task_listing_isolated_between_paired_clients(tmp_path, monkeypatch):
    client, _ = _owner_client(tmp_path, monkeypatch)
    payload_a, challenge_a = _create_pairing(client, telegram_user_id=123456789,
                                               scopes=["tasks:create", "tasks:read"])
    payload_b, challenge_b = _create_pairing(client, telegram_user_id=987654321,
                                               scopes=["tasks:create", "tasks:read"])
    tokens_a = _exchange(client, payload_a, challenge_a).json()
    tokens_b = _exchange(client, payload_b, challenge_b).json()

    task_a = client.post(
        "/integrations/telegram/tasks",
        json={"task_type": "demo.echo", "description": "private task for client A"},
        headers={**_bot_headers(tokens_a, 123456789), "Idempotency-Key": "client-a-task-0001"},
    )
    task_b = client.post(
        "/integrations/telegram/tasks",
        json={"task_type": "demo.echo", "description": "private task for client B"},
        headers={**_bot_headers(tokens_b, 987654321), "Idempotency-Key": "client-b-task-0001"},
    )
    assert task_a.status_code == 201
    assert task_b.status_code == 201

    listed_a = client.get(
        "/integrations/telegram/tasks",
        headers=_bot_headers(tokens_a, 123456789),
    )
    listed_b = client.get(
        "/integrations/telegram/tasks",
        headers=_bot_headers(tokens_b, 987654321),
    )
    assert listed_a.status_code == 200
    assert listed_b.status_code == 200
    assert [item["task_id"] for item in listed_a.json()["tasks"]] == [task_a.json()["task_id"]]
    assert [item["task_id"] for item in listed_b.json()["tasks"]] == [task_b.json()["task_id"]]

    detail_a = client.get(
        f"/integrations/telegram/tasks/{task_a.json()['task_id']}",
        headers=_bot_headers(tokens_a, 123456789),
    )
    detail_b = client.get(
        f"/integrations/telegram/tasks/{task_b.json()['task_id']}",
        headers=_bot_headers(tokens_b, 987654321),
    )
    cross_client = client.get(
        f"/integrations/telegram/tasks/{task_a.json()['task_id']}",
        headers=_bot_headers(tokens_b, 987654321),
    )
    assert detail_a.status_code == 200
    assert detail_a.json()["description"] == "private task for client A"
    assert detail_b.status_code == 200
    assert detail_b.json()["description"] == "private task for client B"
    assert cross_client.status_code == 404
    get_settings.cache_clear()

def test_refresh_rotates_refresh_token_and_rejects_reuse(tmp_path, monkeypatch):
    client, _ = _owner_client(tmp_path, monkeypatch)
    payload, challenge = _create_pairing(client)
    original = _exchange(client, payload, challenge).json()

    rotated_response = client.post(
        "/integrations/telegram/refresh",
        json={
            "refresh_token": original["refresh_token"],
            "telegram_user_id": payload["telegram_user_id"],
        },
    )
    assert rotated_response.status_code == 200
    rotated = rotated_response.json()
    assert rotated["access_token"] != original["access_token"]
    assert rotated["refresh_token"] != original["refresh_token"]
    assert rotated["refresh_expires_in"] == 30 * 24 * 60 * 60

    reused = client.post(
        "/integrations/telegram/refresh",
        json={
            "refresh_token": original["refresh_token"],
            "telegram_user_id": payload["telegram_user_id"],
        },
    )
    assert reused.status_code == 401

    second_rotation = client.post(
        "/integrations/telegram/refresh",
        json={
            "refresh_token": rotated["refresh_token"],
            "telegram_user_id": payload["telegram_user_id"],
        },
    )
    assert second_rotation.status_code == 200
    assert second_rotation.json()["refresh_token"] != rotated["refresh_token"]
    get_settings.cache_clear()



def test_telegram_task_history_paginates_with_client_scoped_cursors(tmp_path, monkeypatch):
    client, database_path = _owner_client(tmp_path, monkeypatch)
    payload_a, challenge_a = _create_pairing(
        client,
        telegram_user_id=123456789,
        scopes=["tasks:create", "tasks:read"],
    )
    payload_b, challenge_b = _create_pairing(
        client,
        telegram_user_id=987654321,
        scopes=["tasks:create", "tasks:read"],
    )
    tokens_a = _exchange(client, payload_a, challenge_a).json()
    tokens_b = _exchange(client, payload_b, challenge_b).json()

    task_b = client.post(
        "/integrations/telegram/tasks",
        json={"task_type": "demo.echo", "description": "older task for client B"},
        headers={**_bot_headers(tokens_b, 987654321), "Idempotency-Key": "pagination-b-0001"},
    )
    assert task_b.status_code == 201

    task_ids_a = []
    for index in range(5):
        response = client.post(
            "/integrations/telegram/tasks",
            json={"task_type": "demo.echo", "description": f"client A task {index}"},
            headers={
                **_bot_headers(tokens_a, 123456789),
                "Idempotency-Key": f"pagination-a-{index:04d}",
            },
        )
        assert response.status_code == 201
        task_ids_a.append(response.json()["task_id"])

    # Equal timestamps exercise the UUID tie-breaker used by keyset pagination.
    fixed_timestamp = "2099-01-01T00:00:00+00:00"
    with sqlite3.connect(database_path) as connection:
        connection.executemany(
            "UPDATE tasks SET created_at = ? WHERE task_id = ?",
            [(fixed_timestamp, task_id) for task_id in task_ids_a],
        )

    first = client.get(
        "/integrations/telegram/tasks",
        params={"limit": 2},
        headers=_bot_headers(tokens_a, 123456789),
    )
    assert first.status_code == 200
    first_page = first.json()
    assert len(first_page["tasks"]) == 2
    assert first_page["has_more"] is True
    assert first_page["next_cursor"]

    second = client.get(
        "/integrations/telegram/tasks",
        params={"limit": 2, "cursor": first_page["next_cursor"]},
        headers=_bot_headers(tokens_a, 123456789),
    )
    assert second.status_code == 200
    second_page = second.json()
    assert len(second_page["tasks"]) == 2
    assert second_page["has_more"] is True
    assert second_page["next_cursor"]

    third = client.get(
        "/integrations/telegram/tasks",
        params={"limit": 2, "cursor": second_page["next_cursor"]},
        headers=_bot_headers(tokens_a, 123456789),
    )
    assert third.status_code == 200
    third_page = third.json()
    assert len(third_page["tasks"]) == 1
    assert third_page["has_more"] is False
    assert third_page["next_cursor"] is None

    paged_ids = [
        item["task_id"]
        for page in (first_page, second_page, third_page)
        for item in page["tasks"]
    ]
    complete = client.get(
        "/integrations/telegram/tasks",
        params={"limit": 50},
        headers=_bot_headers(tokens_a, 123456789),
    )
    assert complete.status_code == 200
    assert paged_ids == [item["task_id"] for item in complete.json()["tasks"]]
    assert len(paged_ids) == len(set(paged_ids)) == len(task_ids_a)

    client_b_page = client.get(
        "/integrations/telegram/tasks",
        params={"limit": 2, "cursor": first_page["next_cursor"]},
        headers=_bot_headers(tokens_b, 987654321),
    )
    assert client_b_page.status_code == 200
    assert [item["task_id"] for item in client_b_page.json()["tasks"]] == [
        task_b.json()["task_id"]
    ]

    invalid_cursor = client.get(
        "/integrations/telegram/tasks",
        params={"cursor": "not-a-valid-cursor"},
        headers=_bot_headers(tokens_a, 123456789),
    )
    assert invalid_cursor.status_code == 422
    get_settings.cache_clear()



def test_telegram_task_result_is_terminal_bounded_and_client_scoped(tmp_path, monkeypatch):
    client, database_path = _owner_client(tmp_path, monkeypatch)
    payload_a, challenge_a = _create_pairing(
        client, telegram_user_id=123456789, scopes=["tasks:create", "tasks:read", "tasks:result"]
    )
    payload_b, challenge_b = _create_pairing(
        client, telegram_user_id=987654321, scopes=["tasks:create", "tasks:read", "tasks:result"]
    )
    payload_read_only, challenge_read_only = _create_pairing(
        client, telegram_user_id=555555555, scopes=["tasks:create", "tasks:read"]
    )
    tokens_a = _exchange(client, payload_a, challenge_a).json()
    tokens_b = _exchange(client, payload_b, challenge_b).json()
    tokens_read_only = _exchange(client, payload_read_only, challenge_read_only).json()

    created = client.post(
        "/integrations/telegram/tasks",
        json={"task_type": "demo.echo", "description": "result owner"},
        headers={**_bot_headers(tokens_a, 123456789), "Idempotency-Key": "result-owner-0001"},
    )
    assert created.status_code == 201
    task_id = created.json()["task_id"]
    pending = client.get(
        f"/integrations/telegram/tasks/{task_id}/result",
        headers=_bot_headers(tokens_a, 123456789),
    )
    assert pending.status_code == 409

    with sqlite3.connect(database_path) as connection:
        connection.execute("UPDATE tasks SET status='succeeded' WHERE task_id=?", (task_id,))

    results = {
        task_id: {"result": {"message": "completed"}, "error_code": None, "attempt_count": 1},
    }
    monkeypatch.setattr(
        "mrhub.api.routes.telegram_integration.WorkerEngine.get_result",
        lambda _worker, requested_id: results.get(str(requested_id)),
    )
    completed = client.get(
        f"/integrations/telegram/tasks/{task_id}/result",
        headers=_bot_headers(tokens_a, 123456789),
    )
    assert completed.status_code == 200
    assert completed.json()["result"]["message"] == "completed"

    cross_client = client.get(
        f"/integrations/telegram/tasks/{task_id}/result",
        headers=_bot_headers(tokens_b, 987654321),
    )
    assert cross_client.status_code == 404

    denied = client.get(
        f"/integrations/telegram/tasks/{task_id}/result",
        headers=_bot_headers(tokens_read_only, 555555555),
    )
    assert denied.status_code == 403

    results[task_id] = {"result": "x" * 33_000}
    oversized = client.get(
        f"/integrations/telegram/tasks/{task_id}/result",
        headers=_bot_headers(tokens_a, 123456789),
    )
    assert oversized.status_code == 413
    get_settings.cache_clear()


def test_telegram_task_cancellation_requires_scope_ownership_and_pending_state(tmp_path, monkeypatch):
    client, database_path = _owner_client(tmp_path, monkeypatch)
    payload_a, challenge_a = _create_pairing(
        client,
        telegram_user_id=123456789,
        scopes=["tasks:create", "tasks:read", "tasks:cancel"],
    )
    payload_b, challenge_b = _create_pairing(
        client,
        telegram_user_id=987654321,
        scopes=["tasks:create", "tasks:read", "tasks:cancel"],
    )
    payload_read_only, challenge_read_only = _create_pairing(
        client,
        telegram_user_id=555555555,
        scopes=["tasks:create", "tasks:read"],
    )
    tokens_a = _exchange(client, payload_a, challenge_a).json()
    tokens_b = _exchange(client, payload_b, challenge_b).json()
    tokens_read_only = _exchange(client, payload_read_only, challenge_read_only).json()

    def create_task(tokens, user_id, key):
        return client.post(
            "/integrations/telegram/tasks",
            json={"task_type": "demo.echo", "description": key},
            headers={**_bot_headers(tokens, user_id), "Idempotency-Key": key},
        )

    task_a = create_task(tokens_a, 123456789, "cancel-owner-a-0001")
    task_b = create_task(tokens_b, 987654321, "cancel-owner-b-0001")
    assert task_a.status_code == task_b.status_code == 201
    task_a_id = task_a.json()["task_id"]
    task_b_id = task_b.json()["task_id"]

    cancelled = client.post(
        f"/integrations/telegram/tasks/{task_a_id}/cancel",
        headers=_bot_headers(tokens_a, 123456789),
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"

    repeated = client.post(
        f"/integrations/telegram/tasks/{task_a_id}/cancel",
        headers=_bot_headers(tokens_a, 123456789),
    )
    assert repeated.status_code == 409

    cross_client = client.post(
        f"/integrations/telegram/tasks/{task_a_id}/cancel",
        headers=_bot_headers(tokens_b, 987654321),
    )
    assert cross_client.status_code == 404

    denied = client.post(
        f"/integrations/telegram/tasks/{task_b_id}/cancel",
        headers=_bot_headers(tokens_read_only, 555555555),
    )
    assert denied.status_code == 403

    with sqlite3.connect(database_path) as connection:
        connection.execute("UPDATE tasks SET status='running' WHERE task_id=?", (task_b_id,))
    running = client.post(
        f"/integrations/telegram/tasks/{task_b_id}/cancel",
        headers=_bot_headers(tokens_b, 987654321),
    )
    assert running.status_code == 409
    get_settings.cache_clear()


def test_telegram_task_list_can_filter_by_status_without_leaking_other_clients(tmp_path, monkeypatch):
    client, database_path = _owner_client(tmp_path, monkeypatch)
    payload_a, challenge_a = _create_pairing(
        client, telegram_user_id=123456789, scopes=["tasks:create", "tasks:read"]
    )
    payload_b, challenge_b = _create_pairing(
        client, telegram_user_id=987654321, scopes=["tasks:create", "tasks:read"]
    )
    tokens_a = _exchange(client, payload_a, challenge_a).json()
    tokens_b = _exchange(client, payload_b, challenge_b).json()

    queued = client.post(
        "/integrations/telegram/tasks",
        json={"task_type": "demo.echo", "description": "keep queued"},
        headers={**_bot_headers(tokens_a, 123456789), "Idempotency-Key": "status-filter-queued"},
    )
    running = client.post(
        "/integrations/telegram/tasks",
        json={"task_type": "demo.echo", "description": "move to running"},
        headers={**_bot_headers(tokens_a, 123456789), "Idempotency-Key": "status-filter-running"},
    )
    other = client.post(
        "/integrations/telegram/tasks",
        json={"task_type": "demo.echo", "description": "other client"},
        headers={**_bot_headers(tokens_b, 987654321), "Idempotency-Key": "status-filter-other"},
    )
    assert queued.status_code == running.status_code == other.status_code == 201
    repository = TaskRepository(database_path)
    repository.initialize()
    JobEngine(repository).transition(UUID(running.json()["task_id"]), TaskStatus.RUNNING)

    queued_page = client.get(
        "/integrations/telegram/tasks",
        params={"status": "queued"},
        headers=_bot_headers(tokens_a, 123456789),
    )
    running_page = client.get(
        "/integrations/telegram/tasks",
        params={"status": "running"},
        headers=_bot_headers(tokens_a, 123456789),
    )
    assert queued_page.status_code == running_page.status_code == 200
    assert [item["task_id"] for item in queued_page.json()["tasks"]] == [queued.json()["task_id"]]
    assert [item["task_id"] for item in running_page.json()["tasks"]] == [running.json()["task_id"]]
    assert other.json()["task_id"] not in {
        item["task_id"] for item in queued_page.json()["tasks"] + running_page.json()["tasks"]
    }
    assert client.get(
        "/integrations/telegram/tasks",
        params={"status": "unknown"},
        headers=_bot_headers(tokens_a, 123456789),
    ).status_code == 422
    get_settings.cache_clear()


def test_telegram_task_event_timeline_is_bounded_and_pairing_scoped(tmp_path, monkeypatch):
    client, database_path = _owner_client(tmp_path, monkeypatch)
    payload_a, challenge_a = _create_pairing(
        client, telegram_user_id=123456789, scopes=["tasks:create", "tasks:read"]
    )
    payload_b, challenge_b = _create_pairing(
        client, telegram_user_id=987654321, scopes=["tasks:create", "tasks:read"]
    )
    tokens_a = _exchange(client, payload_a, challenge_a).json()
    tokens_b = _exchange(client, payload_b, challenge_b).json()
    created = client.post(
        "/integrations/telegram/tasks",
        json={"task_type": "demo.echo", "description": "timeline test"},
        headers={**_bot_headers(tokens_a, 123456789), "Idempotency-Key": "timeline-task-0001"},
    )
    assert created.status_code == 201
    task_id = UUID(created.json()["task_id"])
    repository = TaskRepository(database_path)
    repository.initialize()
    engine = JobEngine(repository)
    engine.transition(task_id, TaskStatus.RUNNING)
    engine.transition(task_id, TaskStatus.SUCCEEDED)

    timeline = client.get(
        f"/integrations/telegram/tasks/{task_id}/events",
        params={"limit": 2},
        headers=_bot_headers(tokens_a, 123456789),
    )
    assert timeline.status_code == 200
    payload = timeline.json()
    assert payload["task_id"] == str(task_id)
    assert payload["count"] == 2
    assert payload["has_more"] is True
    assert isinstance(payload["next_cursor"], str)
    assert all("metadata" in event and "actor_id" not in event for event in payload["events"])

    second_page = client.get(
        f"/integrations/telegram/tasks/{task_id}/events",
        params={"limit": 2, "cursor": payload["next_cursor"]},
        headers=_bot_headers(tokens_a, 123456789),
    )
    assert second_page.status_code == 200
    second_payload = second_page.json()
    assert second_payload["count"] == 1
    assert second_payload["has_more"] is False
    assert second_payload["next_cursor"] is None
    assert len({
        event["event_id"] for event in [*payload["events"], *second_payload["events"]]
    }) == 3
    assert {event["event_type"] for event in [*payload["events"], *second_payload["events"]]} == {
        "task.submitted", "task.status_changed"
    }

    limited = client.get(
        f"/integrations/telegram/tasks/{task_id}/events",
        params={"limit": 0},
        headers=_bot_headers(tokens_a, 123456789),
    )
    cross_client = client.get(
        f"/integrations/telegram/tasks/{task_id}/events",
        headers=_bot_headers(tokens_b, 987654321),
    )
    invalid_cursor = client.get(
        f"/integrations/telegram/tasks/{task_id}/events",
        params={"cursor": "not-a-cursor"},
        headers=_bot_headers(tokens_a, 123456789),
    )
    assert limited.status_code == 422
    assert invalid_cursor.status_code == 422
    assert cross_client.status_code == 404
    get_settings.cache_clear()


def _video_generation_row(generation_id, created_at="2026-11-15T12:00:00+00:00"):
    return {
        "generation_id": str(generation_id),
        "source_analysis_id": str(uuid4()),
        "provider": "local",
        "model": "renderer-v1",
        "status": "queued",
        "provider_job_id": "private-provider-job-id",
        "progress_percent": None,
        "output_asset_id": str(uuid4()),
        "output_bytes": None,
        "output_duration_seconds": None,
        "output_width": None,
        "output_height": None,
        "error_code": None,
        "created_at": created_at,
        "updated_at": created_at,
    }


def test_telegram_video_history_requires_explicit_video_read_scope(tmp_path, monkeypatch):
    client, _ = _owner_client(tmp_path, monkeypatch)
    payload, challenge = _create_pairing(client)
    tokens = _exchange(client, payload, challenge).json()

    response = client.get(
        "/integrations/telegram/video/generations",
        headers=_bot_headers(tokens),
    )

    assert response.status_code == 403
    get_settings.cache_clear()


def test_telegram_video_history_is_bounded_owner_scoped_and_redacts_internal_ids(
    tmp_path, monkeypatch
):
    from mrhub.video_intelligence.generation_jobs import VideoGenerationJobRepository

    client, _ = _owner_client(tmp_path, monkeypatch)
    payload, challenge = _create_pairing(client, scopes=["video:read"])
    tokens = _exchange(client, payload, challenge).json()
    first_id, second_id = uuid4(), uuid4()
    rows = [
        _video_generation_row(first_id),
        _video_generation_row(second_id, "2026-11-14T12:00:00+00:00"),
    ]
    calls = []

    def list_for_owner(
        self, owner_user_id, *, limit=20, before_created_at=None,
        before_generation_id=None
    ):
        calls.append((owner_user_id, limit, before_created_at, before_generation_id))
        return rows

    monkeypatch.setattr(VideoGenerationJobRepository, "list_for_owner", list_for_owner)
    response = client.get(
        "/integrations/telegram/video/generations?limit=1",
        headers=_bot_headers(tokens),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    assert body["has_more"] is True
    assert body["items"][0]["generation_id"] == str(first_id)
    assert "source_analysis_id" not in body["items"][0]
    assert "output_asset_id" not in body["items"][0]
    assert "provider_job_id" not in body["items"][0]
    assert body["next_cursor"]
    assert calls == [("local-owner", 2, None, None)]

    next_page = client.get(
        "/integrations/telegram/video/generations",
        params={"limit": 1, "cursor": body["next_cursor"]},
        headers=_bot_headers(tokens),
    )
    assert next_page.status_code == 200
    assert calls[1][0] == "local-owner"
    assert calls[1][1] == 2
    assert calls[1][2] == rows[0]["created_at"]
    assert calls[1][3] == first_id
    get_settings.cache_clear()


def test_telegram_video_history_rejects_invalid_cursor_and_page_size(tmp_path, monkeypatch):
    client, _ = _owner_client(tmp_path, monkeypatch)
    payload, challenge = _create_pairing(client, scopes=["video:read"])
    tokens = _exchange(client, payload, challenge).json()
    headers = _bot_headers(tokens)

    invalid_cursor = client.get(
        "/integrations/telegram/video/generations",
        params={"cursor": "not-a-valid-cursor!"},
        headers=headers,
    )
    invalid_limit = client.get(
        "/integrations/telegram/video/generations",
        params={"limit": 21},
        headers=headers,
    )

    assert invalid_cursor.status_code == 422
    assert invalid_limit.status_code == 422
    get_settings.cache_clear()


def test_telegram_video_status_is_owner_scoped_and_does_not_expose_provider_ids(
    tmp_path, monkeypatch
):
    from mrhub.video_intelligence.generation_jobs import VideoGenerationJobRepository

    client, _ = _owner_client(tmp_path, monkeypatch)
    payload, challenge = _create_pairing(client, scopes=["video:read"])
    tokens = _exchange(client, payload, challenge).json()
    generation_id = uuid4()
    calls = []

    def get_generation(self, owner_user_id, requested_id):
        calls.append((owner_user_id, requested_id))
        return _video_generation_row(requested_id)

    monkeypatch.setattr(VideoGenerationJobRepository, "get", get_generation)
    response = client.get(
        f"/integrations/telegram/video/generations/{generation_id}",
        headers=_bot_headers(tokens),
    )

    assert response.status_code == 200
    assert response.json()["generation_id"] == str(generation_id)
    assert "provider_job_id" not in response.json()
    assert "output_asset_id" not in response.json()
    assert calls == [("local-owner", generation_id)]
    get_settings.cache_clear()


def test_telegram_video_cancel_requires_separate_scope_and_only_pending_jobs(
    tmp_path, monkeypatch
):
    from mrhub.video_intelligence.generation_jobs import (
        VideoGenerationCancellationConflict,
        VideoGenerationJobRepository,
    )

    client, _ = _owner_client(tmp_path, monkeypatch)
    read_payload, read_challenge = _create_pairing(client, scopes=["video:read"])
    read_tokens = _exchange(client, read_payload, read_challenge).json()
    generation_id = uuid4()
    denied = client.delete(
        f"/integrations/telegram/video/generations/{generation_id}",
        headers=_bot_headers(read_tokens),
    )
    assert denied.status_code == 403

    cancel_payload, cancel_challenge = _create_pairing(
        client, telegram_user_id=987654321, scopes=["video:cancel"]
    )
    cancel_tokens = _exchange(
        client, cancel_payload, cancel_challenge
    ).json()
    calls = []

    def cancel_pending(self, owner_user_id, requested_id):
        calls.append((owner_user_id, requested_id))
        return {
            "generation_id": str(requested_id),
            "status": "cancelled",
            "cancellation_requested": False,
        }

    monkeypatch.setattr(VideoGenerationJobRepository, "cancel_pending", cancel_pending)
    cancelled = client.delete(
        f"/integrations/telegram/video/generations/{generation_id}",
        headers=_bot_headers(cancel_tokens, telegram_user_id=987654321),
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    assert calls == [("local-owner", generation_id)]

    def active_conflict(self, owner_user_id, requested_id):
        raise VideoGenerationCancellationConflict("provider work is already active")

    monkeypatch.setattr(VideoGenerationJobRepository, "cancel_pending", active_conflict)
    blocked = client.delete(
        f"/integrations/telegram/video/generations/{generation_id}",
        headers=_bot_headers(cancel_tokens, telegram_user_id=987654321),
    )
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["code"] == "generation_cancellation_conflict"
    get_settings.cache_clear()


def test_owner_can_update_scopes_for_an_existing_client_without_repairing(
    tmp_path, monkeypatch
):
    from mrhub.video_intelligence.generation_jobs import VideoGenerationJobRepository

    client, _ = _owner_client(tmp_path, monkeypatch)
    payload, challenge = _create_pairing(client)
    tokens = _exchange(client, payload, challenge).json()
    headers = _bot_headers(tokens)

    denied = client.get(
        "/integrations/telegram/video/generations",
        headers=headers,
    )
    assert denied.status_code == 403

    updated = client.put(
        f"/integrations/telegram/clients/{payload['client_id']}/scopes",
        json={"scopes": ["video:read", "video:cancel"]},
    )
    assert updated.status_code == 200
    assert updated.json() == {
        "client_id": payload["client_id"],
        "scopes": ["video:cancel", "video:read"],
    }

    monkeypatch.setattr(
        VideoGenerationJobRepository,
        "list_for_owner",
        lambda self, owner_user_id, **kwargs: [],
    )
    allowed = client.get(
        "/integrations/telegram/video/generations",
        headers=headers,
    )
    assert allowed.status_code == 200
    assert allowed.json()["items"] == []

    missing_generation = client.delete(
        f"/integrations/telegram/video/generations/{uuid4()}",
        headers=headers,
    )
    assert missing_generation.status_code == 404
    get_settings.cache_clear()


def test_owner_scope_update_rejects_duplicates_and_does_not_change_foreign_or_revoked_clients(
    tmp_path, monkeypatch
):
    client, _ = _owner_client(tmp_path, monkeypatch)
    payload, challenge = _create_pairing(client)
    _exchange(client, payload, challenge)

    duplicate = client.put(
        f"/integrations/telegram/clients/{payload['client_id']}/scopes",
        json={"scopes": ["video:read", "video:read"]},
    )
    assert duplicate.status_code == 422

    foreign = client.put(
        f"/integrations/telegram/clients/{uuid4()}/scopes",
        json={"scopes": ["video:read"]},
    )
    assert foreign.status_code == 404

    revoked = client.post(
        f"/integrations/telegram/clients/{payload['client_id']}/revoke"
    )
    assert revoked.status_code == 200
    after_revoke = client.put(
        f"/integrations/telegram/clients/{payload['client_id']}/scopes",
        json={"scopes": ["video:read"]},
    )
    assert after_revoke.status_code == 404
    get_settings.cache_clear()



def test_telegram_video_render_drafts_are_owner_scoped_and_redacted(tmp_path, monkeypatch):
    from uuid import uuid4

    from mrhub.video_intelligence.jobs import VideoAnalysisJobRepository
    from mrhub.video_intelligence.timeline_drafts import VideoTimelineDraftRepository

    client, _ = _owner_client(tmp_path, monkeypatch)
    payload, challenge = _create_pairing(client, scopes=["video:read"])
    tokens = _exchange(client, payload, challenge).json()
    analysis_id = uuid4()
    draft_id = uuid4()
    calls = []

    def get_analysis(self, owner_user_id, requested_id):
        calls.append(("analysis", owner_user_id, requested_id))
        return {"status": "completed", "result": {"assets": []}}

    def list_drafts(self, owner_user_id, requested_id, limit=5):
        calls.append(("drafts", owner_user_id, requested_id, limit))
        return [{
            "draft_id": str(draft_id),
            "asset_id": "private-source-asset",
            "version": 3,
            "duration_seconds": 10,
            "aspect_ratio": "9:16",
            "renderer_timeline": {"private": "timeline"},
            "renderer_timeline_sha256": "a" * 64,
            "updated_at": "2026-11-16T10:00:00+00:00",
        }]

    monkeypatch.setattr(VideoAnalysisJobRepository, "get", get_analysis)
    monkeypatch.setattr(VideoTimelineDraftRepository, "list_for_analysis", list_drafts)
    response = client.get(
        "/integrations/telegram/video/render-drafts",
        params={"analysis_id": str(analysis_id)},
        headers=_bot_headers(tokens),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["analysis_id"] == str(analysis_id)
    assert body["count"] == 1
    assert body["drafts"][0] == {
        "draft_id": str(draft_id),
        "version": 3,
        "duration_seconds": 10,
        "aspect_ratio": "9:16",
        "renderer_ready": True,
        "updated_at": "2026-11-16T10:00:00+00:00",
    }
    assert calls == [
        ("analysis", "local-owner", analysis_id),
        ("drafts", "local-owner", analysis_id, 5),
    ]
    get_settings.cache_clear()


def test_telegram_video_render_submission_requires_video_render_scope_and_is_idempotent(
    tmp_path, monkeypatch
):
    from types import SimpleNamespace
    from uuid import uuid4

    from mrhub.video_intelligence.jobs import VideoAnalysisJobRepository
    from mrhub.video_intelligence.render_jobs import VideoRenderJobRepository
    from mrhub.video_intelligence.render_snapshot import VideoRenderTimelineSnapshot
    from mrhub.video_intelligence.timeline_drafts import VideoTimelineDraftRepository

    client, _ = _owner_client(tmp_path, monkeypatch)
    draft_id = uuid4()
    analysis_id = uuid4()
    render_id = uuid4()
    snapshot_id = uuid4()
    read_payload, read_challenge = _create_pairing(client, scopes=["video:read"])
    read_tokens = _exchange(client, read_payload, read_challenge).json()
    denied = client.post(
        "/integrations/telegram/video/renders",
        json={"draft_id": str(draft_id)},
        headers={**_bot_headers(read_tokens), "Idempotency-Key": "telegram:123:1:video-render"},
    )
    assert denied.status_code == 403

    payload, challenge = _create_pairing(
        client, telegram_user_id=987654321, scopes=["video:render"]
    )
    tokens = _exchange(client, payload, challenge).json()
    source_asset_id = "2c83d1c5-1d8d-4c29-8a3d-4dd0e0b10a00"
    timeline_data = {
        "schema_version": "1.0",
        "output_aspect_ratio": "16:9",
        "requested_duration_seconds": 3,
        "actual_duration_seconds": 3.0,
        "duration_shortfall_seconds": 0.0,
        "video_track": [{
            "clip_id": "clip-001",
            "source_asset_id": source_asset_id,
            "source_scene_index": 0,
            "source_start_seconds": 0.0,
            "source_end_seconds": 3.0,
            "timeline_start_seconds": 0.0,
            "timeline_end_seconds": 3.0,
            "transition_in": "none",
        }],
        "audio_analysis_status": "not_requested",
        "audio_render_status": "not_implemented",
        "timeline_status": "validated_cut_only",
        "render_status": "not_implemented",
    }
    draft = {
        "draft_id": str(draft_id),
        "analysis_id": str(analysis_id),
        "version": 4,
        "renderer_timeline": timeline_data,
        "renderer_timeline_sha256": "b" * 64,
    }
    calls = {}

    monkeypatch.setattr(
        VideoTimelineDraftRepository,
        "get",
        lambda self, owner_user_id, requested_id: (
            draft if owner_user_id == "local-owner" and requested_id == draft_id else None
        ),
    )
    monkeypatch.setattr(
        VideoAnalysisJobRepository,
        "get",
        lambda self, owner_user_id, requested_id: (
            {
                "status": "completed",
                "result": {"assets": [{"asset_id": source_asset_id}]},
            }
            if owner_user_id == "local-owner" and requested_id == analysis_id
            else None
        ),
    )

    def create_snapshot(cls, **kwargs):
        calls["snapshot"] = kwargs
        return SimpleNamespace(snapshot_id=snapshot_id)

    monkeypatch.setattr(
        VideoRenderTimelineSnapshot, "create", classmethod(create_snapshot)
    )

    def submit(self, owner_user_id, requested_analysis_id, idempotency_key, *, snapshot=None):
        calls["submit"] = (owner_user_id, requested_analysis_id, idempotency_key, snapshot)
        return ({
            "render_id": str(render_id),
            "task_id": str(uuid4()),
            "analysis_id": str(analysis_id),
            "status": "accepted",
            "created_at": "2026-11-16T10:00:00+00:00",
            "snapshot_id": str(snapshot_id),
        }, True)

    monkeypatch.setattr(VideoRenderJobRepository, "submit", submit)
    key = "telegram:987654321:42:video-render"
    response = client.post(
        "/integrations/telegram/video/renders",
        json={"draft_id": str(draft_id)},
        headers={**_bot_headers(tokens, telegram_user_id=987654321), "Idempotency-Key": key},
    )

    assert response.status_code == 202
    body = response.json()
    assert body["render_id"] == str(render_id)
    assert body["draft_id"] == str(draft_id)
    assert body["draft_version"] == 4
    assert body["snapshot_id"] == str(snapshot_id)
    assert body["render_kind"] == "deterministic_ffmpeg"
    assert body["created"] is True
    assert "task_id" not in body
    assert calls["snapshot"]["owner_user_id"] == "local-owner"
    assert calls["snapshot"]["analysis_id"] == analysis_id
    assert calls["snapshot"]["draft_id"] == draft_id
    assert calls["snapshot"]["draft_version"] == 4
    assert calls["snapshot"]["analysis_source_asset_ids"] == [source_asset_id]
    assert calls["submit"][:3] == ("local-owner", analysis_id, key)
    assert calls["submit"][3] is not None
    get_settings.cache_clear()


def test_telegram_video_render_status_and_cancel_use_separate_scopes(tmp_path, monkeypatch):
    from uuid import uuid4

    from mrhub.video_intelligence.render_jobs import VideoRenderJobRepository

    client, _ = _owner_client(tmp_path, monkeypatch)
    render_id = uuid4()
    read_payload, read_challenge = _create_pairing(client, scopes=["video:read"])
    read_tokens = _exchange(client, read_payload, read_challenge).json()
    calls = []

    def get_render(self, owner_user_id, requested_id):
        calls.append(("get", owner_user_id, requested_id))
        return {
            "render_id": str(requested_id),
            "status": "completed",
            "output_asset_id": "private-output-asset",
            "output_metadata": {"file_size": 1234, "duration_seconds": 3.0},
        }

    monkeypatch.setattr(VideoRenderJobRepository, "get", get_render)
    response = client.get(
        f"/integrations/telegram/video/renders/{render_id}",
        headers=_bot_headers(read_tokens),
    )
    assert response.status_code == 200
    assert response.json()["render_kind"] == "deterministic_ffmpeg"
    assert response.json()["output_available"] is True
    assert "output_asset_id" not in response.json()
    assert "private-output-asset" not in response.text

    denied = client.delete(
        f"/integrations/telegram/video/renders/{render_id}",
        headers=_bot_headers(read_tokens),
    )
    assert denied.status_code == 403

    cancel_payload, cancel_challenge = _create_pairing(
        client, telegram_user_id=987654321, scopes=["video:cancel"]
    )
    cancel_tokens = _exchange(client, cancel_payload, cancel_challenge).json()

    def cancel_render(self, owner_user_id, requested_id):
        calls.append(("cancel", owner_user_id, requested_id))
        return {
            "render_id": str(requested_id),
            "status": "running",
            "cancellation_requested": True,
        }

    monkeypatch.setattr(VideoRenderJobRepository, "cancel", cancel_render)
    cancelled = client.delete(
        f"/integrations/telegram/video/renders/{render_id}",
        headers=_bot_headers(cancel_tokens, telegram_user_id=987654321),
    )
    assert cancelled.status_code == 200
    assert cancelled.json() == {
        "render_id": str(render_id),
        "render_kind": "deterministic_ffmpeg",
        "status": "running",
        "cancellation_requested": True,
    }
    assert calls == [
        ("get", "local-owner", render_id),
        ("cancel", "local-owner", render_id),
    ]
    get_settings.cache_clear()



def test_telegram_memory_dream_preview_requires_memory_scope_and_is_read_only(tmp_path, monkeypatch):
    from mrhub.memory.repository import MemoryRepository

    client, _ = _owner_client(tmp_path, monkeypatch)
    denied_payload, denied_challenge = _create_pairing(client, scopes=["status:read"])
    denied_tokens = _exchange(client, denied_payload, denied_challenge).json()
    denied = client.post(
        "/integrations/telegram/memory/dream/preview",
        json={"limit": 100},
        headers=_bot_headers(denied_tokens),
    )
    assert denied.status_code == 403

    payload, challenge = _create_pairing(
        client, telegram_user_id=987654321, scopes=["memory:search"]
    )
    tokens = _exchange(client, payload, challenge).json()
    repository = MemoryRepository(get_settings().database_path)
    repository.create(
        "local-owner",
        {
            "category": "engineering",
            "content": "SQLite FTS5 provides local lexical memory retrieval",
        },
    )
    repository.create(
        "local-owner",
        {
            "category": "engineering",
            "content": "SQLite FTS5 provides local lexical memory retrieval",
        },
    )

    response = client.post(
        "/integrations/telegram/memory/dream/preview",
        json={"limit": 100},
        headers=_bot_headers(tokens, telegram_user_id=987654321),
    )
    assert response.status_code == 200
    assert response.json()["proposal_count"] == 1
    assert response.json()["state_changed"] is False
    assert response.json()["proposals"][0]["requires_owner_review"] is True
    assert len(repository.list_entries("local-owner")) == 2
    get_settings.cache_clear()



def test_telegram_memory_validation_requires_scope_and_is_read_only(tmp_path, monkeypatch):
    client, _ = _owner_client(tmp_path, monkeypatch)

    denied_payload, denied_challenge = _create_pairing(client, scopes=["status:read"])
    denied_tokens = _exchange(client, denied_payload, denied_challenge).json()
    denied = client.post(
        "/integrations/telegram/memory/validate/preview",
        json={"limit": 100},
        headers=_bot_headers(denied_tokens),
    )
    assert denied.status_code == 403

    payload, challenge = _create_pairing(
        client, telegram_user_id=987654322, scopes=["memory:search"]
    )
    tokens = _exchange(client, payload, challenge).json()
    repository = MemoryRepository(get_settings().database_path)
    repository.create(
        "local-owner",
        {
            "category": "preferences",
            "content": "Tea is preferred by user every morning",
            "confidence": 0.9,
            "verification_status": "user_approved",
        },
    )
    repository.create(
        "local-owner",
        {
            "category": "preferences",
            "content": "Tea is not preferred by user every morning",
            "confidence": 0.4,
        },
    )

    response = client.post(
        "/integrations/telegram/memory/validate/preview",
        json={"limit": 100},
        headers=_bot_headers(tokens, telegram_user_id=987654322),
    )
    assert response.status_code == 200
    assert response.json()["contradiction_count"] == 1
    assert response.json()["unverified_count"] == 1
    assert response.json()["state_changed"] is False
    assert len(repository.list_entries("local-owner")) == 2
    get_settings.cache_clear()


def test_telegram_memory_entry_review_requires_separate_read_and_write_scopes(tmp_path, monkeypatch):
    client, database_path = _owner_client(tmp_path, monkeypatch)
    repository = MemoryRepository(database_path)
    entry = repository.create(
        "local-owner",
        {
            "category": "preferences",
            "content": "The owner prefers concise technical summaries",
            "confidence": 0.65,
            "verification_status": "user_authored",
        },
    )
    memory_id = entry["memory_id"]

    read_payload, read_challenge = _create_pairing(
        client, telegram_user_id=333333333, scopes=["memory:search"]
    )
    read_tokens = _exchange(client, read_payload, read_challenge).json()
    headers = _bot_headers(read_tokens, 333333333)

    inspected = client.get(
        f"/integrations/telegram/memory/{memory_id}", headers=headers
    )
    assert inspected.status_code == 200
    assert inspected.json()["content"] == entry["content"]
    assert inspected.json()["verification_status"] == "user_authored"

    denied = client.post(
        f"/integrations/telegram/memory/{memory_id}/approve", headers=headers
    )
    assert denied.status_code == 403
    assert repository.get("local-owner", UUID(memory_id))["verification_status"] == "user_authored"

    write_payload, write_challenge = _create_pairing(
        client, telegram_user_id=444444444, scopes=["memory:write"]
    )
    write_tokens = _exchange(client, write_payload, write_challenge).json()
    write_headers = _bot_headers(write_tokens, 444444444)

    approved = client.post(
        f"/integrations/telegram/memory/{memory_id}/approve", headers=write_headers
    )
    assert approved.status_code == 200
    assert approved.json() == {
        "memory_id": memory_id,
        "category": "preferences",
        "verification_status": "user_approved",
        "changed": True,
    }
    assert repository.get("local-owner", UUID(memory_id))["verification_status"] == "user_approved"

    repeated = client.post(
        f"/integrations/telegram/memory/{memory_id}/approve", headers=write_headers
    )
    assert repeated.status_code == 200
    assert repeated.json()["changed"] is False

    missing = client.post(
        "/integrations/telegram/memory/aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa/approve",
        headers=write_headers,
    )
    assert missing.status_code == 404

    with sqlite3.connect(database_path) as connection:
        audit = connection.execute(
            "SELECT event_type, actor_type, actor_id FROM audit_events "
            "WHERE event_type = 'memory.approved' ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
    assert audit == ("memory.approved", "telegram_client", write_payload["client_id"])
    get_settings.cache_clear()


def test_telegram_video_scene_jobs_require_explicit_scopes_and_are_owner_scoped(
    tmp_path, monkeypatch
):
    client, database_path = _owner_client(tmp_path, monkeypatch)
    asset = client.post(
        "/content/assets",
        headers={"X-File-Name": "telegram-scene.mp4", "Content-Type": "video/mp4"},
        content=b"\\x00\\x00\\x00\\x18ftypisom0000",
    )
    assert asset.status_code == 201
    asset_id = asset.json()["asset_id"]

    payload, challenge = _create_pairing(
        client,
        telegram_user_id=555555555,
        scopes=["video:analyze", "video:read", "video:cancel"],
    )
    assert challenge["scopes"] == ["video:analyze", "video:read", "video:cancel"]
    tokens = _exchange(client, payload, challenge).json()
    headers = _bot_headers(tokens, 555555555)

    accepted = client.post(
        "/integrations/telegram/video/scene-jobs",
        json={"asset_id": asset_id, "threshold": 0.4, "max_scene_changes": 12},
        headers={**headers, "Idempotency-Key": "telegram-scene:555555555:1"},
    )
    assert accepted.status_code == 202
    job_id = accepted.json()["job_id"]
    assert "task_id" not in accepted.json()

    replay = client.post(
        "/integrations/telegram/video/scene-jobs",
        json={"asset_id": asset_id, "threshold": 0.4, "max_scene_changes": 12},
        headers={**headers, "Idempotency-Key": "telegram-scene:555555555:1"},
    )
    assert replay.status_code == 200
    assert replay.json()["job_id"] == job_id

    status = client.get(
        f"/integrations/telegram/video/scene-jobs/{job_id}", headers=headers
    )
    assert status.status_code == 200
    assert status.json()["status"] == "queued"
    assert "task_id" not in status.json()
    assert "source_asset_id" not in status.json()

    history_second = client.post(
        "/integrations/telegram/video/scene-jobs",
        json={"asset_id": asset_id, "threshold": 0.4, "max_scene_changes": 12},
        headers={**headers, "Idempotency-Key": "telegram-scene:555555555:2"},
    )
    assert history_second.status_code == 202
    history_one = client.get(
        "/integrations/telegram/video/scene-jobs",
        params={"limit": 1},
        headers=headers,
    )
    assert history_one.status_code == 200
    assert history_one.json()["has_more"] is True
    assert history_one.json()["items"][0]["job_id"] == history_second.json()["job_id"]
    history_two = client.get(
        "/integrations/telegram/video/scene-jobs",
        params={"limit": 1, "cursor": history_one.json()["next_cursor"]},
        headers=headers,
    )
    assert history_two.status_code == 200
    assert history_two.json()["items"][0]["job_id"] == job_id

    cancelled = client.post(
        f"/integrations/telegram/video/scene-jobs/{job_id}/cancel", headers=headers
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"

    with sqlite3.connect(database_path) as connection:
        audit = connection.execute(
            "SELECT event_type, actor_type, actor_id FROM audit_events "
            "WHERE event_type = 'video.scene_job.submitted' ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
    assert audit == (
        "video.scene_job.submitted", "telegram_client", payload["client_id"]
    )
    get_settings.cache_clear()


def test_telegram_video_scene_submission_is_denied_without_video_analyze_scope(
    tmp_path, monkeypatch
):
    client, _database_path = _owner_client(tmp_path, monkeypatch)
    asset = client.post(
        "/content/assets",
        headers={"X-File-Name": "scope-test.mp4", "Content-Type": "video/mp4"},
        content=b"\\x00\\x00\\x00\\x18ftypisom0000",
    )
    assert asset.status_code == 201
    payload, challenge = _create_pairing(
        client, telegram_user_id=666666666, scopes=["video:read"]
    )
    tokens = _exchange(client, payload, challenge).json()
    denied = client.post(
        "/integrations/telegram/video/scene-jobs",
        json={"asset_id": asset.json()["asset_id"]},
        headers={
            **_bot_headers(tokens, 666666666),
            "Idempotency-Key": "telegram-scene:666666666:1",
        },
    )
    assert denied.status_code == 403
    get_settings.cache_clear()
