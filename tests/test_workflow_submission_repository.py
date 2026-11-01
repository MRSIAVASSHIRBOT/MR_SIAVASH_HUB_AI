import sqlite3

import pytest

from mrhub.agents.submission_repository import (
    IdempotencyConflict,
    SubmissionStateError,
    WorkflowSubmissionRepository,
)


def make_repository(tmp_path):
    database_path = tmp_path / "submissions.sqlite3"
    repository = WorkflowSubmissionRepository(database_path)
    repository.initialize()
    connection = sqlite3.connect(database_path)
    connection.execute(
        """INSERT INTO auth_users
           (user_id, username, salt, password_hash, created_at)
           VALUES ('user-1', 'user1', 'salt', 'hash', '2026-01-01T00:00:00+00:00')"""
    )
    connection.commit()
    connection.close()
    return repository


def test_reservation_is_atomic_and_repeated_same_request_returns_existing(tmp_path):
    repository = make_repository(tmp_path)

    first = repository.reserve("user-1", "/agent/workflows", "key-1", "digest-1")
    repeated = repository.reserve("user-1", "/agent/workflows", "key-1", "digest-1")

    assert first["state"] == "reserved"
    assert first["created"] is True
    assert repeated["state"] == "reserved"
    assert repeated["created"] is False
    assert repeated["created_at"] == first["created_at"]


def test_reusing_key_for_different_request_fails_closed(tmp_path):
    repository = make_repository(tmp_path)
    repository.reserve("user-1", "/agent/workflows", "key-1", "digest-1")

    with pytest.raises(IdempotencyConflict, match="different request"):
        repository.reserve("user-1", "/agent/workflows", "key-1", "digest-2")


def test_owner_and_endpoint_have_independent_key_scopes(tmp_path):
    repository = make_repository(tmp_path)
    repository.reserve("user-1", "/agent/workflows", "same-key", "digest-1")

    other_endpoint = repository.reserve("user-1", "/agent/plans", "same-key", "digest-2")
    connection = sqlite3.connect(repository.database_path)
    connection.execute(
        """INSERT INTO auth_users
           (user_id, username, salt, password_hash, created_at)
           VALUES ('user-2', 'user2', 'salt', 'hash', '2026-01-01T00:00:00+00:00')"""
    )
    connection.commit()
    connection.close()
    other_owner = repository.reserve("user-2", "/agent/workflows", "same-key", "digest-3")

    assert other_endpoint["created"] is True
    assert other_owner["created"] is True


def test_binding_is_idempotent_and_cannot_be_repointed(tmp_path):
    repository = make_repository(tmp_path)
    repository.reserve("user-1", "/agent/workflows", "key-1", "digest-1")

    bound = repository.bind(
        "user-1", "/agent/workflows", "key-1", "digest-1", "workflow-1", "task-1"
    )
    repeated = repository.bind(
        "user-1", "/agent/workflows", "key-1", "digest-1", "workflow-1", "task-1"
    )

    assert bound["state"] == "bound"
    assert bound["workflow_id"] == "workflow-1"
    assert repeated["workflow_id"] == "workflow-1"
    with pytest.raises(SubmissionStateError, match="another execution"):
        repository.bind(
            "user-1", "/agent/workflows", "key-1", "digest-1", "workflow-2", "task-2"
        )


def test_failed_reservation_cannot_be_reused_or_bound(tmp_path):
    repository = make_repository(tmp_path)
    repository.reserve("user-1", "/agent/workflows", "key-1", "digest-1")
    repository.mark_failed("user-1", "/agent/workflows", "key-1", "digest-1")

    assert repository.reserve(
        "user-1", "/agent/workflows", "key-1", "digest-1"
    )["state"] == "failed"
    with pytest.raises(SubmissionStateError, match="Only a reserved"):
        repository.bind(
            "user-1", "/agent/workflows", "key-1", "digest-1", "workflow-1", "task-1"
        )
