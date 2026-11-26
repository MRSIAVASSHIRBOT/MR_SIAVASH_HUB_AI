from datetime import UTC, datetime, timedelta
from uuid import uuid4

from client_helpers import authenticated_client
from mrhub.config import get_settings
from mrhub.memory.dreaming import MemoryDreamingEngine
from mrhub.memory.repository import MemoryRepository
from mrhub.memory.validation import MemoryValidationEngine


def _owner_id(repository: MemoryRepository) -> str:
    with repository.tasks._connection() as connection:
        row = connection.execute("SELECT user_id FROM auth_users LIMIT 1").fetchone()
    assert row is not None
    return str(row["user_id"])


def _expiry(days: int) -> str:
    return (datetime.now(UTC) + timedelta(days=days)).isoformat()


def test_ephemeral_memory_requires_expiry_and_enforces_stage_ttl():
    client = authenticated_client()
    base = {
        "category": "lifecycle",
        "content": "working memory lifecycle retention test marker",
        "memory_stage": "working",
    }

    missing_expiry = client.post("/memory", json=base)
    assert missing_expiry.status_code == 422

    excessive_expiry = client.post(
        "/memory", json={**base, "expires_at": _expiry(8)}
    )
    assert excessive_expiry.status_code == 422

    accepted = client.post(
        "/memory", json={**base, "expires_at": _expiry(2)}
    )
    assert accepted.status_code == 201
    assert accepted.json()["memory_stage"] == "working"


def test_lesson_candidate_is_expiring_and_remains_in_owner_review_queue():
    client = authenticated_client()
    candidate = client.post(
        "/memory",
        json={
            "category": "lessons",
            "memory_type": "procedural",
            "memory_stage": "lesson_candidate",
            "content": "candidate lesson must receive owner review before retention",
            "expires_at": _expiry(20),
        },
    )
    assert candidate.status_code == 201
    assert candidate.json()["memory_stage"] == "lesson_candidate"

    repository = MemoryRepository(get_settings().database_path)
    result = MemoryValidationEngine(get_settings().database_path).preview(
        _owner_id(repository)
    )
    item = next(
        row for row in result["review_queue"]
        if row["memory_id"] == candidate.json()["memory_id"]
    )
    assert item["memory_stage"] == "lesson_candidate"
    assert item["reasons"] == ["lesson_candidate_pending_review"]
    assert result["state_changed"] is False


def test_search_can_filter_by_memory_lifecycle_stage():
    client = authenticated_client()
    marker = "stagefilterbeacon retained and working lifecycle record"
    working = client.post(
        "/memory",
        json={
            "category": "search",
            "content": marker,
            "memory_stage": "working",
            "expires_at": _expiry(1),
        },
    )
    retained = client.post(
        "/memory",
        json={"category": "search", "content": marker},
    )
    assert working.status_code == retained.status_code == 201

    response = client.post(
        "/memory/search",
        json={"query": "stagefilterbeacon lifecycle", "memory_stages": ["working"]},
    )
    assert response.status_code == 200
    assert [row["memory_id"] for row in response.json()["results"]] == [
        working.json()["memory_id"]
    ]


def test_stage_transition_requires_retention_and_rejects_overlong_ttl():
    client = authenticated_client()
    created = client.post(
        "/memory",
        json={"category": "transition", "content": "retained stage transition marker"},
    )
    assert created.status_code == 201
    memory_id = created.json()["memory_id"]

    missing_expiry = client.patch(
        f"/memory/{memory_id}", json={"memory_stage": "working"}
    )
    assert missing_expiry.status_code == 422

    excessive_expiry = client.patch(
        f"/memory/{memory_id}",
        json={"memory_stage": "lesson_candidate", "expires_at": _expiry(31)},
    )
    assert excessive_expiry.status_code == 422

    moved = client.patch(
        f"/memory/{memory_id}",
        json={"memory_stage": "working", "expires_at": _expiry(3)},
    )
    assert moved.status_code == 200
    assert moved.json()["memory_stage"] == "working"


def test_dreaming_only_considers_retained_entries():
    client = authenticated_client()
    shared = "architecture capability planner evidence workflow consolidation"
    first = client.post(
        "/memory",
        json={"category": "dreaming", "content": shared + " retained entry alpha"},
    )
    second = client.post(
        "/memory",
        json={"category": "dreaming", "content": shared + " retained entry beta"},
    )
    candidate_a = client.post(
        "/memory",
        json={
            "category": "dreaming",
            "content": shared + " candidate entry gamma",
            "memory_stage": "lesson_candidate",
            "expires_at": _expiry(10),
        },
    )
    candidate_b = client.post(
        "/memory",
        json={
            "category": "dreaming",
            "content": shared + " candidate entry delta",
            "memory_stage": "lesson_candidate",
            "expires_at": _expiry(10),
        },
    )
    assert all(
        response.status_code == 201
        for response in (first, second, candidate_a, candidate_b)
    )

    result = MemoryDreamingEngine(get_settings().database_path).preview(
        _owner_id(MemoryRepository(get_settings().database_path)),
        threshold=0.75,
    )
    assert result["proposal_count"] >= 1
    assert all(
        proposal["canonical_memory_id"] not in {
            candidate_a.json()["memory_id"],
            candidate_b.json()["memory_id"],
        }
        and proposal["candidate_memory_id"] not in {
            candidate_a.json()["memory_id"],
            candidate_b.json()["memory_id"],
        }
        for proposal in result["proposals"]
    )
    assert result["state_changed"] is False


def test_legacy_insert_defaults_to_retained_after_schema_upgrade():
    authenticated_client()
    repository = MemoryRepository(get_settings().database_path)
    owner_id = _owner_id(repository)
    memory_id = str(uuid4())
    now = datetime.now(UTC).isoformat()

    # Simulate an older application writer that does not know about memory_stage.
    with repository.tasks._connection() as connection:
        connection.execute(
            """
            INSERT INTO memory_entries (
                memory_id, owner_user_id, scope, memory_type, category, content,
                provenance, confidence, verification_status, created_at,
                updated_at, expires_at
            ) VALUES (?, ?, 'private', 'unspecified', ?, ?, ?, 0.7,
                      'user_authored', ?, ?, NULL)
            """,
            (
                memory_id,
                owner_id,
                "compatibility",
                "legacy memory compatibility marker",
                "legacy-writer",
                now,
                now,
            ),
        )

    from uuid import UUID

    migrated = repository.get(owner_id, UUID(memory_id))
    assert migrated is not None
    assert migrated["memory_stage"] == "retained"

    with repository.tasks._connection() as connection:
        migration = connection.execute(
            "SELECT version, name FROM schema_migrations WHERE version = 58"
        ).fetchone()
    assert migration is not None
    assert migration["name"] == "owner_scoped_memory_lifecycle_stages"


def _insert_memory_row(
    repository: MemoryRepository,
    *,
    owner_id: str,
    content: str,
    expires_at: str | None,
) -> str:
    memory_id = str(uuid4())
    now = datetime.now(UTC).isoformat()
    with repository.tasks._connection() as connection:
        connection.execute(
            """
            INSERT INTO memory_entries (
                memory_id, owner_user_id, scope, memory_type, memory_stage,
                category, content, provenance, confidence, verification_status,
                created_at, updated_at, expires_at
            ) VALUES (?, ?, 'private', 'unspecified', 'working', ?, ?, ?, 0.7,
                      'user_authored', ?, ?, ?)
            """,
            (
                memory_id,
                owner_id,
                "expiry-cleanup",
                content,
                "expiry-cleanup-test",
                now,
                now,
                expires_at,
            ),
        )
    return memory_id


def test_memory_access_deletes_expired_rows_in_owner_scoped_batches():
    client = authenticated_client()
    repository = MemoryRepository(get_settings().database_path)
    owner_id = _owner_id(repository)
    other_owner_id = "expiry-cleanup-other-owner"
    now = datetime.now(UTC)
    expired_at = (now - timedelta(days=1)).isoformat()
    future_at = (now + timedelta(days=1)).isoformat()

    with repository.tasks._connection() as connection:
        connection.execute(
            """
            INSERT INTO auth_users (
                user_id, username, salt, password_hash, created_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                other_owner_id,
                "expiry-cleanup-other-owner@example.test",
                "salt",
                "hash",
                now.isoformat(),
            ),
        )

    expired_owner_id = _insert_memory_row(
        repository,
        owner_id=owner_id,
        content="owner expired cleanup search fixture",
        expires_at=expired_at,
    )
    active_owner_id = _insert_memory_row(
        repository,
        owner_id=owner_id,
        content="owner active cleanup search fixture",
        expires_at=future_at,
    )
    expired_other_id = _insert_memory_row(
        repository,
        owner_id=other_owner_id,
        content="other owner expired cleanup fixture",
        expires_at=expired_at,
    )

    listed = repository.list_entries(owner_id, limit=100)
    assert [item["memory_id"] for item in listed] == [active_owner_id]

    with repository.tasks._connection() as connection:
        remaining = {
            row["memory_id"]
            for row in connection.execute(
                "SELECT memory_id FROM memory_entries WHERE memory_id IN (?, ?, ?)",
                (expired_owner_id, active_owner_id, expired_other_id),
            )
        }
        fts_rows = {
            row["memory_id"]
            for row in connection.execute(
                "SELECT memory_id FROM memory_entries_fts WHERE memory_id IN (?, ?, ?)",
                (expired_owner_id, active_owner_id, expired_other_id),
            )
        }

    assert remaining == {active_owner_id, expired_other_id}
    assert fts_rows == {active_owner_id, expired_other_id}


def test_memory_expiry_cleanup_respects_a_strict_batch_limit():
    client = authenticated_client()
    repository = MemoryRepository(get_settings().database_path)
    owner_id = _owner_id(repository)
    expired_at = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    expired_ids = {
        _insert_memory_row(
            repository,
            owner_id=owner_id,
            content=f"bounded expiry cleanup fixture {index}",
            expires_at=expired_at,
        )
        for index in range(3)
    }

    assert repository.delete_expired(owner_id, limit=2) == 2
    with repository.tasks._connection() as connection:
        remaining = {
            row["memory_id"]
            for row in connection.execute(
                "SELECT memory_id FROM memory_entries WHERE owner_user_id = ?",
                (owner_id,),
            )
            if row["memory_id"] in expired_ids
        }

    assert len(remaining) == 1
    assert repository.delete_expired(owner_id, limit=500) == 1


def test_expired_memory_cannot_be_revived_by_an_owner_update():
    client = authenticated_client()
    repository = MemoryRepository(get_settings().database_path)
    owner_id = _owner_id(repository)
    expired_at = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    memory_id = _insert_memory_row(
        repository,
        owner_id=owner_id,
        content="expired memory cannot be revived marker",
        expires_at=expired_at,
    )

    from uuid import UUID

    result = repository.update(
        owner_id,
        UUID(memory_id),
        {"memory_stage": "retained", "expires_at": None},
    )

    assert result is None
    with repository.tasks._connection() as connection:
        row = connection.execute(
            "SELECT 1 FROM memory_entries WHERE memory_id = ? AND owner_user_id = ?",
            (memory_id, owner_id),
        ).fetchone()
    assert row is None
