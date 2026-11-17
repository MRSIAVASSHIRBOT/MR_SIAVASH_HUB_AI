from pathlib import Path

from mrhub.memory.dreaming import MemoryDreamingEngine
from mrhub.memory.repository import MemoryRepository


def _create_owner(repository: MemoryRepository, owner_id: str) -> None:
    with repository.tasks._connection() as connection:
        connection.execute(
            "INSERT INTO auth_users (user_id, username, salt, password_hash, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (owner_id, owner_id, "00", "00", "2026-01-01T00:00:00+00:00"),
        )


def test_dreaming_preview_proposes_duplicate_notes_without_mutating(tmp_path: Path) -> None:
    repository = MemoryRepository(tmp_path / "memory.sqlite3")
    _create_owner(repository, "owner-a")
    first = repository.create(
        "owner-a",
        {
            "category": "engineering",
            "content": "SQLite FTS5 provides local lexical memory retrieval",
            "provenance": "first note",
        },
    )
    second = repository.create(
        "owner-a",
        {
            "category": "engineering",
            "content": "SQLite FTS5 provides local lexical memory retrieval",
            "provenance": "second note",
        },
    )

    result = MemoryDreamingEngine(tmp_path / "memory.sqlite3").preview("owner-a")

    assert result["engine"] == "deterministic_memory_review_v1"
    assert result["proposal_count"] == 1
    proposal = result["proposals"][0]
    assert {proposal["canonical_memory_id"], proposal["candidate_memory_id"]} == {
        first["memory_id"], second["memory_id"]
    }
    assert proposal["requires_owner_review"] is True
    assert proposal["automatic_change"] is False
    assert result["state_changed"] is False
    assert len(repository.list_entries("owner-a")) == 2


def test_dreaming_preview_does_not_compare_different_categories(tmp_path: Path) -> None:
    repository = MemoryRepository(tmp_path / "memory.sqlite3")
    _create_owner(repository, "owner-a")
    repository.create(
        "owner-a",
        {"category": "engineering", "content": "SQLite FTS5 provides local lexical memory retrieval"},
    )
    repository.create(
        "owner-a",
        {"category": "personal", "content": "SQLite FTS5 provides local lexical memory retrieval"},
    )

    result = MemoryDreamingEngine(tmp_path / "memory.sqlite3").preview("owner-a")
    assert result["proposal_count"] == 0


def test_dreaming_preview_is_owner_scoped_and_bounded(tmp_path: Path) -> None:
    repository = MemoryRepository(tmp_path / "memory.sqlite3")
    _create_owner(repository, "owner-a")
    repository.create(
        "owner-a",
        {"category": "engineering", "content": "SQLite FTS5 provides local lexical memory retrieval"},
    )
    _create_owner(repository, "owner-b")
    repository.create(
        "owner-b",
        {"category": "engineering", "content": "SQLite FTS5 provides local lexical memory retrieval"},
    )

    result = MemoryDreamingEngine(tmp_path / "memory.sqlite3").preview("owner-a")
    assert result["entries_scanned"] == 1
    assert result["proposal_count"] == 0


def test_dreaming_preview_rejects_unsafe_bounds(tmp_path: Path) -> None:
    engine = MemoryDreamingEngine(tmp_path / "memory.sqlite3")
    try:
        engine.preview("owner-a", limit=101)
    except ValueError as exc:
        assert "limit" in str(exc)
    else:
        raise AssertionError("Expected bounded limit validation")



def test_memory_dream_preview_api_is_authenticated_and_audits_counts_only() -> None:
    from client_helpers import authenticated_client
    from mrhub.config import get_settings
    from mrhub.memory.repository import MemoryRepository

    client = authenticated_client()
    first = client.post(
        "/memory",
        json={
            "category": "engineering",
            "content": "SQLite FTS5 provides local lexical memory retrieval",
        },
    )
    second = client.post(
        "/memory",
        json={
            "category": "engineering",
            "content": "SQLite FTS5 provides local lexical memory retrieval",
        },
    )
    assert first.status_code == 201
    assert second.status_code == 201

    preview = client.post("/memory/dream/preview", json={"limit": 100})
    assert preview.status_code == 200
    payload = preview.json()
    assert payload["proposal_count"] == 1
    assert payload["state_changed"] is False
    assert payload["proposals"][0]["requires_owner_review"] is True

    repository = MemoryRepository(get_settings().database_path)
    with repository.tasks._connection() as connection:
        audit = connection.execute(
            "SELECT metadata_json FROM audit_events "
            "WHERE event_type = 'memory.dream_previewed' ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
    assert audit is not None
    assert "SQLite FTS5" not in audit["metadata_json"]
    assert len(repository.list_entries("local-owner")) >= 2
