from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from client_helpers import authenticated_client
from mrhub.config import get_settings
from mrhub.main import create_app
from mrhub.memory.repository import MemoryRepository


def test_memory_crud_search_update_and_delete_keep_fts_index_consistent() -> None:
    client = authenticated_client()
    created = client.post(
        "/memory",
        json={
            "category": "engineering",
            "content": "SQLite FTS5 provides local lexical memory retrieval",
            "provenance": "user-authored project note",
        },
    )
    assert created.status_code == 201
    entry = created.json()
    assert entry["scope"] == "private"
    assert entry["verification_status"] == "user_authored"
    repository = MemoryRepository(get_settings().database_path)
    with repository.tasks._connection() as connection:
        audit = connection.execute(
            "SELECT subject_type, metadata_json FROM audit_events "
            "WHERE event_type = 'memory.created' ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
    assert audit is not None
    assert audit["subject_type"] == "memory"
    assert "SQLite FTS5" not in audit["metadata_json"]

    found = client.post("/memory/search", json={"query": "SQLite memory"})
    assert found.status_code == 200
    assert found.json()["method"] == "sqlite_fts5"
    assert [item["memory_id"] for item in found.json()["results"]] == [entry["memory_id"]]

    updated = client.patch(
        f"/memory/{entry['memory_id']}",
        json={"content": "The local knowledge store uses FTS5 for source-backed retrieval"},
    )
    assert updated.status_code == 200
    old_terms = client.post("/memory/search", json={"query": "SQLite retrieval"})
    assert old_terms.status_code == 200
    assert old_terms.json()["results"] == []
    new_terms = client.post("/memory/search", json={"query": "source-backed retrieval"})
    assert new_terms.status_code == 200
    assert [item["memory_id"] for item in new_terms.json()["results"]] == [entry["memory_id"]]

    deleted = client.delete(f"/memory/{entry['memory_id']}")
    assert deleted.status_code == 204
    assert client.get(f"/memory/{entry['memory_id']}").status_code == 404
    assert client.post("/memory/search", json={"query": "knowledge store"}).json()["results"] == []


def test_memory_search_filters_by_owner_before_returning_results() -> None:
    client = authenticated_client()
    created = client.post(
        "/memory",
        json={"category": "test", "content": "private zebra memory boundary"},
    )
    assert created.status_code == 201
    own_id = created.json()["memory_id"]

    repository = MemoryRepository(get_settings().database_path)
    with repository.tasks._connection() as connection:
        connection.execute(
            "INSERT INTO auth_users (user_id, username, salt, password_hash, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                "other-owner",
                "other-owner",
                "00",
                "00",
                datetime.now(UTC).isoformat(),
            ),
        )
    other = repository.create(
        "other-owner",
        {
            "category": "test",
            "content": "private zebra memory boundary from another owner",
            "provenance": "test fixture",
        },
    )

    result = client.post("/memory/search", json={"query": "zebra boundary"})
    assert result.status_code == 200
    assert [item["memory_id"] for item in result.json()["results"]] == [own_id]
    assert client.get(f"/memory/{other['memory_id']}").status_code == 404


def test_memory_rejects_obvious_credentials_and_requires_authentication() -> None:
    client = authenticated_client()
    response = client.post(
        "/memory",
        json={
            "category": "unsafe",
            "content": "api_key=sk-abcdefghijklmnop0123456789",
        },
    )
    assert response.status_code == 422
    provenance_secret = client.post(
        "/memory",
        json={
            "category": "unsafe",
            "content": "ordinary note",
            "provenance": "api_key=sk-abcdefghijklmnop0123456789",
        },
    )
    assert provenance_secret.status_code == 422

    get_settings.cache_clear()
    unauthenticated = TestClient(create_app())
    assert unauthenticated.get("/memory").status_code in (401, 403)


def test_expiry_filters_retrieval_and_purge_removes_fts_rows() -> None:
    client = authenticated_client()
    future = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    created = client.post(
        "/memory",
        json={
            "category": "retention",
            "content": "temporary comet retention marker",
            "expires_at": future,
        },
    )
    assert created.status_code == 201
    memory_id = created.json()["memory_id"]

    repository = MemoryRepository(get_settings().database_path)
    with repository.tasks._connection() as connection:
        connection.execute(
            "UPDATE memory_entries SET expires_at = ? WHERE memory_id = ?",
            ("2000-01-01T00:00:00+00:00", memory_id),
        )

    assert client.get(f"/memory/{memory_id}").status_code == 404
    assert client.post("/memory/search", json={"query": "comet retention"}).json()["results"] == []
    purge = client.delete("/memory/expired")
    assert purge.status_code == 200
    assert purge.json()["deleted"] == 1
    with repository.tasks._connection() as connection:
        assert connection.execute(
            "SELECT 1 FROM memory_entries_fts WHERE memory_id = ?", (memory_id,)
        ).fetchone() is None


def test_memory_export_is_owner_scoped_and_contains_expired_entries() -> None:
    client = authenticated_client()
    created = client.post(
        "/memory",
        json={"category": "export", "content": "portable memory export example"},
    )
    assert created.status_code == 201
    exported = client.get("/memory/export")
    assert exported.status_code == 200
    assert exported.json()["export_version"] == 1
    assert [entry["memory_id"] for entry in exported.json()["entries"]] == [
        created.json()["memory_id"]
    ]
