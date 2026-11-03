from client_helpers import authenticated_client
from mrhub.config import get_settings
from mrhub.knowledge.repository import KnowledgeRepository


def _create_document():
    client = authenticated_client()
    created = client.post(
        "/knowledge/documents",
        json={
            "title": "Integrity fixture",
            "content": "DNS resolver configuration is part of this integrity fixture.",
            "source_ref": "local-note:integrity-fixture",
        },
    )
    assert created.status_code == 201
    document = created.json()
    repository = KnowledgeRepository(get_settings().database_path)
    return document, repository


def test_search_rejects_chunk_content_that_no_longer_matches_its_hash():
    document, repository = _create_document()
    with repository.tasks._connection() as connection:
        connection.execute(
            "UPDATE knowledge_chunks SET content = ? WHERE document_id = ?",
            ("tampered resolver evidence", document["document_id"]),
        )

    assert repository.search("local-owner", "tampered resolver", limit=5) == []


def test_search_rejects_document_content_that_no_longer_matches_its_hash():
    document, repository = _create_document()
    with repository.tasks._connection() as connection:
        connection.execute(
            "UPDATE knowledge_documents SET content = ? WHERE document_id = ?",
            ("tampered document content", document["document_id"]),
        )

    assert repository.search("local-owner", "DNS resolver", limit=5) == []


def test_search_rejects_source_hash_that_disagrees_with_document_hash():
    document, repository = _create_document()
    with repository.tasks._connection() as connection:
        connection.execute(
            "UPDATE knowledge_sources SET content_hash = ? WHERE source_id = ?",
            ("f" * 64, document["source_id"]),
        )

    assert repository.search("local-owner", "DNS resolver", limit=5) == []


def test_search_rejects_chunk_offsets_that_do_not_match_document_content():
    document, repository = _create_document()
    with repository.tasks._connection() as connection:
        connection.execute(
            """
            UPDATE knowledge_chunks
            SET start_offset = 1, end_offset = 10
            WHERE document_id = ?
            """,
            (document["document_id"],),
        )

    assert repository.search("local-owner", "DNS resolver", limit=5) == []
