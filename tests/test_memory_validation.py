from datetime import UTC, datetime, timedelta
from pathlib import Path

from mrhub.memory.repository import MemoryRepository
from mrhub.memory.validation import MemoryValidationEngine


def _owner(repository: MemoryRepository, owner_id: str) -> None:
    with repository.tasks._connection() as connection:
        connection.execute(
            "INSERT INTO auth_users (user_id, username, salt, password_hash, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (owner_id, owner_id, "00", "00", datetime.now(UTC).isoformat()),
        )


def test_validation_flags_polarity_conflicts_without_mutating_memory(tmp_path: Path) -> None:
    repository = MemoryRepository(tmp_path / "validation.sqlite3")
    _owner(repository, "owner-a")
    first = repository.create(
        "owner-a",
        {
            "category": "preferences",
            "content": "Tea is preferred by user every morning",
            "confidence": 0.9,
            "verification_status": "user_approved",
        },
    )
    second = repository.create(
        "owner-a",
        {
            "category": "preferences",
            "content": "Tea is not preferred by user every morning",
            "confidence": 0.4,
        },
    )

    result = MemoryValidationEngine(tmp_path / "validation.sqlite3").preview("owner-a")

    assert result["contradiction_count"] == 1
    proposal = result["contradictions"][0]
    assert set(proposal["memory_ids"]) == {first["memory_id"], second["memory_id"]}
    assert proposal["requires_owner_review"] is True
    assert proposal["automatic_change"] is False
    assert result["state_changed"] is False
    assert result["unverified_count"] == 1
    assert len(repository.list_entries("owner-a")) == 2


def test_validation_supports_persian_negation_and_category_separation(tmp_path: Path) -> None:
    repository = MemoryRepository(tmp_path / "validation.sqlite3")
    _owner(repository, "owner-a")
    repository.create(
        "owner-a",
        {"category": "preferences", "content": "کاربر هر روز چای سبز دوست دارد"},
    )
    repository.create(
        "owner-a",
        {"category": "preferences", "content": "کاربر هر روز چای سبز دوست ندارد"},
    )
    repository.create(
        "owner-a",
        {"category": "health", "content": "کاربر هر روز چای سبز دوست ندارد"},
    )

    result = MemoryValidationEngine(tmp_path / "validation.sqlite3").preview("owner-a")
    assert result["contradiction_count"] == 1


def test_validation_reports_expired_and_unverified_entries(tmp_path: Path) -> None:
    repository = MemoryRepository(tmp_path / "validation.sqlite3")
    _owner(repository, "owner-a")
    repository.create(
        "owner-a",
        {
            "category": "temporary",
            "content": "Temporary project context should expire",
            "expires_at": datetime.now(UTC) - timedelta(days=1),
        },
    )
    repository.create(
        "owner-a",
        {
            "category": "notes",
            "content": "An unverified note remains available for owner review",
            "confidence": 0.3,
        },
    )

    result = MemoryValidationEngine(tmp_path / "validation.sqlite3").preview("owner-a")
    assert result["expired_count"] == 1
    assert result["unverified_count"] == 1
    assert result["expired_entries"][0]["reason"] == "expired"
    assert result["state_changed"] is False


def test_validation_is_owner_scoped_and_bounds_are_enforced(tmp_path: Path) -> None:
    database = tmp_path / "validation.sqlite3"
    repository = MemoryRepository(database)
    _owner(repository, "owner-a")
    _owner(repository, "owner-b")
    repository.create(
        "owner-b",
        {"category": "preferences", "content": "User prefers tea every morning"},
    )
    repository.create(
        "owner-b",
        {"category": "preferences", "content": "User does not prefer tea every morning"},
    )

    engine = MemoryValidationEngine(database)
    result = engine.preview("owner-a")
    assert result["entries_scanned"] == 0
    assert result["contradiction_count"] == 0

    for kwargs in ({"limit": 101}, {"threshold": 0.5}):
        try:
            engine.preview("owner-a", **kwargs)
        except ValueError:
            pass
        else:
            raise AssertionError("Expected bounded validation parameters")
