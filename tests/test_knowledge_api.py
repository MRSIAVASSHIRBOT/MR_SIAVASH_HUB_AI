from datetime import UTC, datetime

from fastapi.testclient import TestClient

from client_helpers import authenticated_client
from mrhub.config import get_settings
from mrhub.knowledge.repository import KnowledgeRepository
from mrhub.main import create_app


def test_document_ingestion_chunks_content_and_returns_citation_bearing_search_results() -> None:
    client = authenticated_client()
    content = "Project reference.\n" + "\n".join(
        f"Section {index}: worker lease fencing and durable checkpoint recovery."
        for index in range(90)
    )
    created = client.post(
        "/knowledge/documents",
        json={
            "title": "Workflow Recovery Notes",
            "content": content,
            "source_ref": "local-note:workflow-recovery.md",
            "language": "en",
            "trust_classification": "user_reviewed",
        },
    )
    assert created.status_code == 201
    document = created.json()
    assert document["chunk_count"] > 1
    assert document["trust_classification"] == "user_reviewed"
    assert document["source_ref"] == "local-note:workflow-recovery.md"
    assert len(document["content_hash"]) == 64

    search = client.post(
        "/knowledge/search",
        json={"query": "lease fencing checkpoint", "limit": 5},
    )
    assert search.status_code == 200
    body = search.json()
    assert body["method"] == "sqlite_fts5"
    assert "not automatically injected" in body["warning"]
    assert body["results"]
    result = body["results"][0]
    assert result["document_id"] == document["document_id"]
    assert result["title"] == "Workflow Recovery Notes"
    assert result["citation_ref"].startswith(
        f"knowledge://documents/{document['document_id']}#chunk-"
    )
    assert result["start_offset"] < result["end_offset"]
    assert len(result["chunk_hash"]) == 64
    assert result["trust_classification"] == "user_reviewed"


def test_knowledge_search_is_owner_scoped_and_delete_removes_fts_index_rows() -> None:
    client = authenticated_client()
    own = client.post(
        "/knowledge/documents",
        json={
            "title": "Private Source",
            "content": "Nebula lease fencing owner isolation phrase",
        },
    )
    assert own.status_code == 201
    own_id = own.json()["document_id"]

    repository = KnowledgeRepository(get_settings().database_path)
    with repository.tasks._connection() as connection:
        connection.execute(
            "INSERT INTO auth_users (user_id, username, salt, password_hash, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                "knowledge-other-owner",
                "knowledge-other-owner",
                "00",
                "00",
                datetime.now(UTC).isoformat(),
            ),
        )
    other = repository.create_document(
        "knowledge-other-owner",
        title="Another Owner Source",
        content="Nebula lease fencing owner isolation phrase",
    )
    search = client.post("/knowledge/search", json={"query": "Nebula isolation"})
    assert search.status_code == 200
    assert {item["document_id"] for item in search.json()["results"]} == {own_id}
    assert client.get(f"/knowledge/documents/{other['document_id']}").status_code == 404

    deleted = client.delete(f"/knowledge/documents/{own_id}")
    assert deleted.status_code == 204
    assert client.get(f"/knowledge/documents/{own_id}").status_code == 404
    assert client.post(
        "/knowledge/search", json={"query": "Nebula isolation"}
    ).json()["results"] == []
    with repository.tasks._connection() as connection:
        assert connection.execute(
            "SELECT 1 FROM knowledge_chunks_fts WHERE document_id = ?", (own_id,)
        ).fetchone() is None


def test_knowledge_export_is_owner_scoped_and_preserves_source_provenance() -> None:
    client = authenticated_client()
    created = client.post(
        "/knowledge/documents",
        json={
            "title": "Export Fixture",
            "content": "A compact source-backed knowledge export fixture.",
            "source_ref": "user-note:export-fixture",
        },
    )
    assert created.status_code == 201

    exported = client.get("/knowledge/export")
    assert exported.status_code == 200
    assert exported.json()["export_version"] == 1
    assert len(exported.json()["documents"]) == 1
    record = exported.json()["documents"][0]
    assert record["document_id"] == created.json()["document_id"]
    assert record["source_ref"] == "user-note:export-fixture"
    assert record["content"] == "A compact source-backed knowledge export fixture."


def test_knowledge_ingestion_enforces_size_limits_and_does_not_fetch_source_refs() -> None:
    client = authenticated_client()
    oversized = client.post(
        "/knowledge/documents",
        json={"title": "Oversized", "content": "x" * 100_001},
    )
    assert oversized.status_code == 422

    # A URL-like provenance label is stored as a reference only. Ingestion never
    # makes outbound requests or crawls the supplied origin.
    created = client.post(
        "/knowledge/documents",
        json={
            "title": "Reference Only",
            "content": "The supplied origin is a label, not a fetch instruction.",
            "source_ref": "https://example.invalid/private-doc",
        },
    )
    assert created.status_code == 201
    assert created.json()["source_ref"] == "https://example.invalid/private-doc"


def test_knowledge_routes_require_authentication() -> None:
    get_settings.cache_clear()
    client = TestClient(create_app())
    assert client.get("/knowledge/documents").status_code in (401, 403)
