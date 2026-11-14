import hashlib
import sqlite3
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from mrhub.config import get_settings
from mrhub.domain.tasks import TaskStatus
from mrhub.infrastructure.database import TaskRepository
from mrhub.jobs.engine import JobEngine
from mrhub.main import create_app


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
        params={"limit": 50},
        headers=_bot_headers(tokens_a, 123456789),
    )
    assert timeline.status_code == 200
    payload = timeline.json()
    assert payload["task_id"] == str(task_id)
    assert payload["count"] == 3
    assert {event["event_type"] for event in payload["events"]} == {
        "task.submitted", "task.status_changed"
    }
    assert all("metadata" in event and "actor_id" not in event for event in payload["events"])

    limited = client.get(
        f"/integrations/telegram/tasks/{task_id}/events",
        params={"limit": 0},
        headers=_bot_headers(tokens_a, 123456789),
    )
    cross_client = client.get(
        f"/integrations/telegram/tasks/{task_id}/events",
        headers=_bot_headers(tokens_b, 987654321),
    )
    assert limited.status_code == 422
    assert cross_client.status_code == 404
    get_settings.cache_clear()
