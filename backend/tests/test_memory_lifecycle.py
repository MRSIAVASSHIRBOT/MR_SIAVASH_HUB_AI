from datetime import UTC, datetime, timedelta

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


def test_existing_records_default_to_retained_after_schema_upgrade():
    client = authenticated_client()
    response = client.post(
        "/memory",
        json={"category": "compatibility", "content": "legacy memory compatibility marker"},
    )
    assert response.status_code == 201
    assert response.json()["memory_stage"] == "retained"

    repository = MemoryRepository(get_settings().database_path)
    with repository.tasks._connection() as connection:
        migration = connection.execute(
            "SELECT version, name FROM schema_migrations WHERE version = 58"
        ).fetchone()
    assert migration is not None
    assert migration["name"] == "owner_scoped_memory_lifecycle_stages"
