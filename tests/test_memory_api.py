from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
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
    assert entry["memory_type"] == "unspecified"
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


def test_memory_type_is_persisted_filtered_and_updated() -> None:
    client = authenticated_client()
    created = {}
    for memory_type in ("episodic", "semantic", "procedural"):
        response = client.post(
            "/memory",
            json={
                "memory_type": memory_type,
                "category": "apollo",
                "content": "Apollo mission memory classification marker",
            },
        )
        assert response.status_code == 201
        created[memory_type] = response.json()["memory_id"]
        assert response.json()["memory_type"] == memory_type

    episodic = client.post(
        "/memory/search",
        json={"query": "Apollo mission", "memory_types": ["episodic"]},
    )
    assert episodic.status_code == 200
    assert [item["memory_id"] for item in episodic.json()["results"]] == [
        created["episodic"]
    ]

    updated = client.patch(
        f"/memory/{created['episodic']}",
        json={"memory_type": "procedural"},
    )
    assert updated.status_code == 200
    assert updated.json()["memory_type"] == "procedural"

    old_type = client.post(
        "/memory/search",
        json={"query": "Apollo mission", "memory_types": ["episodic"]},
    )
    assert old_type.status_code == 200
    assert old_type.json()["results"] == []

    new_type = client.post(
        "/memory/search",
        json={"query": "Apollo mission", "memory_types": ["procedural"]},
    )
    assert new_type.status_code == 200
    assert {
        item["memory_id"] for item in new_type.json()["results"]
    } == {created["episodic"], created["procedural"]}


def test_memory_type_validation_rejects_unknown_values_and_null_updates() -> None:
    client = authenticated_client()
    invalid = client.post(
        "/memory",
        json={
            "memory_type": "working",
            "category": "invalid",
            "content": "This must not be persisted",
        },
    )
    assert invalid.status_code == 422

    created = client.post(
        "/memory",
        json={"category": "valid", "content": "A valid memory record"},
    )
    assert created.status_code == 201
    invalid_update = client.patch(
        f"/memory/{created.json()['memory_id']}",
        json={"memory_type": None},
    )
    assert invalid_update.status_code == 422

    invalid_search = client.post(
        "/memory/search",
        json={"query": "valid record", "memory_types": ["working"]},
    )
    assert invalid_search.status_code == 422


@pytest.mark.parametrize("field", ["content", "provenance"])
@pytest.mark.parametrize(
    "credential",
    [
        "password=not-a-real-password",
        "sk-abcdefghijklmnop",
        "ghp_abcdefghijklmnopqrst",
        "xoxb-abcdefghijklmnop",
        "-----BEGIN PRIVATE KEY-----",
        "Bearer abcdefghijklmnopqrstuvwxyz123456",
    ],
)
def test_memory_rejects_credential_patterns_on_create_and_update(
    field: str, credential: str
) -> None:
    client = authenticated_client()
    unsafe_payload = {
        "category": "security",
        "content": "ordinary engineering note",
        "provenance": "user-authored",
    }
    unsafe_payload[field] = credential
    assert client.post("/memory", json=unsafe_payload).status_code == 422

    created = client.post(
        "/memory",
        json={
            "category": "security",
            "content": "A note about how a secret manager works",
            "provenance": "user-authored",
        },
    )
    assert created.status_code == 201
    updated = client.patch(
        f"/memory/{created.json()['memory_id']}",
        json={field: credential},
    )
    assert updated.status_code == 422


@pytest.mark.parametrize("field", ["content", "provenance"])
def test_memory_repository_rejects_non_text_values(field: str) -> None:
    client = authenticated_client()
    repository = MemoryRepository(get_settings().database_path)
    invalid_create = {"category": "security", "content": "safe note"}
    invalid_create[field] = {"unexpected": "object"}
    with pytest.raises(TypeError, match="Memory fields must be text"):
        repository.create("owner-test", invalid_create)

    created = client.post(
        "/memory",
        json={"category": "security", "content": "safe repository update fixture"},
    )
    assert created.status_code == 201
    with pytest.raises(TypeError, match="Memory fields must be text"):
        repository.update(
            "owner-test",
            UUID(created.json()["memory_id"]),
            {field: ["not", "text"]},
        )


def test_memory_search_ranks_owner_approved_matches_with_trust_signals() -> None:
    client = authenticated_client()
    content = "SQLite FTS5 local memory retrieval quality marker"
    unverified = client.post(
        "/memory",
        json={
            "category": "engineering",
            "content": content,
            "confidence": 0.99,
            "verification_status": "user_authored",
        },
    )
    verified = client.post(
        "/memory",
        json={
            "category": "engineering",
            "content": content,
            "confidence": 0.80,
            "verification_status": "user_approved",
        },
    )
    assert unverified.status_code == verified.status_code == 201

    response = client.post(
        "/memory/search",
        json={"query": "SQLite FTS5 local memory retrieval quality marker", "limit": 10},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["method"] == "sqlite_fts5"
    assert payload["ranking"]["scheme"] == "hybrid_fts5_owner_attestation_freshness_v1"
    assert payload["ranking"]["owner_approval_is_self_attested"] is True
    assert payload["ranking"]["confidence_is_owner_supplied"] is True
    assert payload["ranking"]["weights"] == {
        "lexical": 0.70,
        "confidence": 0.15,
        "owner_approved": 0.10,
        "freshness": 0.05,
    }

    results = payload["results"]
    assert [item["memory_id"] for item in results] == [
        verified.json()["memory_id"],
        unverified.json()["memory_id"],
    ]
    signals = results[0]["retrieval"]["signals"]
    assert signals["lexical"] == 1.0
    assert signals["owner_approved"] == 1.0
    assert results[0]["retrieval"]["scheme"] == "hybrid_fts5_owner_attestation_freshness_v1"
    assert results[0]["retrieval"]["score"] > results[1]["retrieval"]["score"]


def test_memory_search_uses_freshness_as_a_deterministic_tie_break_signal() -> None:
    client = authenticated_client()
    content = "SQLite freshness ranking tie fixture token"
    stale = client.post(
        "/memory",
        json={
            "category": "engineering",
            "content": content,
            "confidence": 0.8,
            "verification_status": "user_approved",
        },
    )
    fresh = client.post(
        "/memory",
        json={
            "category": "engineering",
            "content": content,
            "confidence": 0.8,
            "verification_status": "user_approved",
        },
    )
    assert stale.status_code == fresh.status_code == 201

    repository = MemoryRepository(get_settings().database_path)
    with repository.tasks._connection() as connection:
        connection.execute(
            "UPDATE memory_entries SET updated_at = ? WHERE memory_id = ?",
            ("2020-01-01T00:00:00+00:00", stale.json()["memory_id"]),
        )
        connection.execute(
            "UPDATE memory_entries SET updated_at = ? WHERE memory_id = ?",
            (datetime.now(UTC).isoformat(), fresh.json()["memory_id"]),
        )

    response = client.post(
        "/memory/search",
        json={"query": "SQLite freshness ranking tie fixture token", "limit": 10},
    )
    assert response.status_code == 200
    results = response.json()["results"]
    assert [item["memory_id"] for item in results] == [
        fresh.json()["memory_id"],
        stale.json()["memory_id"],
    ]
    assert results[0]["retrieval"]["signals"]["freshness"] > (
        results[1]["retrieval"]["signals"]["freshness"]
    )

def test_memory_repository_rejects_non_string_memory_type_updates() -> None:
    client = authenticated_client()
    created = client.post(
        "/memory",
        json={
            "category": "engineering",
            "content": "Typed memory repository update validation",
        },
    )
    assert created.status_code == 201

    repository = MemoryRepository(get_settings().database_path)
    with pytest.raises(ValueError, match="Unsupported memory type"):
        repository.update(
            "local-owner",
            UUID(created.json()["memory_id"]),
            {"memory_type": []},
        )


@pytest.mark.parametrize("confidence", [True, False, "0.7", -0.1, 1.1])
def test_memory_create_rejects_coercible_or_out_of_range_confidence(confidence):
    client = authenticated_client()
    response = client.post(
        "/memory",
        json={
            "category": "confidence-validation",
            "content": "Confidence input validation fixture",
            "confidence": confidence,
        },
    )
    assert response.status_code == 422


@pytest.mark.parametrize("raw_number", ["NaN", "Infinity", "-Infinity"])
def test_memory_create_rejects_non_finite_confidence_without_invalid_error_json(raw_number):
    client = authenticated_client()
    response = client.post(
        "/memory",
        content=(
            '{"category":"confidence-validation",'
            '"content":"Non-finite confidence fixture",'
            f'"confidence":{raw_number}' + "}"
        ),
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 422
    assert response.json()["detail"]


@pytest.mark.parametrize("confidence", [True, "0.5", -0.1, 1.1])
def test_memory_update_rejects_coercible_or_out_of_range_confidence(confidence):
    client = authenticated_client()
    created = client.post(
        "/memory",
        json={
            "category": "confidence-validation",
            "content": "Confidence update validation fixture",
        },
    )
    assert created.status_code == 201
    response = client.patch(
        f"/memory/{created.json()['memory_id']}",
        json={"confidence": confidence},
    )
    assert response.status_code == 422


@pytest.mark.parametrize("raw_number", ["NaN", "Infinity", "-Infinity"])
def test_memory_update_rejects_non_finite_confidence_without_invalid_error_json(raw_number):
    client = authenticated_client()
    created = client.post(
        "/memory",
        json={
            "category": "confidence-validation",
            "content": "Confidence update validation fixture",
        },
    )
    assert created.status_code == 201
    response = client.patch(
        f"/memory/{created.json()['memory_id']}",
        content=f'{{"confidence":{raw_number}' + "}",
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 422
    assert response.json()["detail"]


def test_memory_preview_and_search_numeric_controls_are_strict():
    client = authenticated_client()
    requests = [
        client.post("/memory/search", json={"query": "numeric boundary", "limit": True}),
        client.post("/memory/dream/preview", json={"limit": True}),
        client.post("/memory/validate/preview", json={"limit": True}),
        client.post("/memory/dream/preview", json={"similarity_threshold": True}),
        client.post("/memory/validate/preview", json={"similarity_threshold": "0.72"}),
    ]
    assert [response.status_code for response in requests] == [422] * len(requests)


@pytest.mark.parametrize("raw_number", ["NaN", "Infinity", "-Infinity"])
@pytest.mark.parametrize(
    ("path", "field"),
    [
        ("/memory/dream/preview", "similarity_threshold"),
        ("/memory/validate/preview", "similarity_threshold"),
    ],
)
def test_memory_preview_rejects_non_finite_thresholds(raw_number, path, field):
    client = authenticated_client()
    response = client.post(
        path,
        content=f'{{"{field}":{raw_number}' + "}",
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 422
    assert response.json()["detail"]


@pytest.mark.parametrize(
    "confidence",
    [True, "0.7", float("nan"), float("inf"), float("-inf"), -0.1, 1.1, 10**1000],
)
def test_memory_repository_rejects_invalid_confidence_on_create_and_update(confidence):
    client = authenticated_client()
    created = client.post(
        "/memory",
        json={
            "category": "confidence-validation",
            "content": "Repository confidence boundary fixture",
        },
    )
    assert created.status_code == 201
    repository = MemoryRepository(get_settings().database_path)

    with pytest.raises(ValueError, match="Confidence must be a finite number"):
        repository.create(
            "local-owner",
            {
                "category": "confidence-validation",
                "content": "Invalid confidence must not persist",
                "confidence": confidence,
            },
        )

    with pytest.raises(ValueError, match="Confidence must be a finite number"):
        repository.update(
            "local-owner",
            UUID(created.json()["memory_id"]),
            {"confidence": confidence},
        )


def test_memory_repository_rejects_boolean_search_limits():
    repository = MemoryRepository(get_settings().database_path)
    with pytest.raises(ValueError, match="positive integer"):
        repository.search("local-owner", "numeric boundary", limit=True)
