import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest

from mrhub.agents.submission_repository import (
    IdempotencyConflict,
    SubmissionStateError,
    WorkflowSubmissionRepository,
)
from mrhub.domain.tasks import TaskRecord
from mrhub.jobs.recovery import WorkflowRecoveryError, WorkflowRecoveryRepository


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



def test_concurrent_duplicate_submissions_create_one_reservation(tmp_path):
    repository = make_repository(tmp_path)

    def submit(_):
        return repository.reserve(
            "user-1", "/agent/workflows", "concurrent-key", "same-digest"
        )

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(submit, range(24)))

    assert sum(result["created"] for result in results) == 1
    assert {result["state"] for result in results} == {"reserved"}
    assert len({result["created_at"] for result in results}) == 1


def test_workflow_and_submission_binding_commit_atomically(tmp_path):
    repository = make_repository(tmp_path)
    digest = "a" * 64
    repository.reserve("user-1", "/agent/workflows", "atomic-key", digest)
    recovery = WorkflowRecoveryRepository(repository.database_path)

    workflow_id = recovery.create_run(
        digest,
        [{"step_number": 1, "kind": "provider_selection", "name": "provider_selection"}],
        task=TaskRecord(task_type="agent.workflow", description="test workflow"),
        owner_user_id="user-1",
        submission=("user-1", "/agent/workflows", "atomic-key", digest),
    )

    connection = sqlite3.connect(repository.database_path)
    row = connection.execute(
        "SELECT state, workflow_id, task_id FROM workflow_submission_keys WHERE idempotency_key = ?",
        ("atomic-key",),
    ).fetchone()
    workflow = connection.execute(
        "SELECT task_id, status FROM workflow_runs WHERE workflow_id = ?", (str(workflow_id),)
    ).fetchone()
    task = connection.execute(
        "SELECT status FROM tasks WHERE task_id = ?", (row[2],)
    ).fetchone()
    connection.close()

    assert row == ("bound", str(workflow_id), workflow[0])
    assert workflow[1] == "queued"
    assert task[0] == "queued"


def test_failed_atomic_binding_rolls_back_job_and_workflow_creation(tmp_path):
    repository = make_repository(tmp_path)
    digest = "b" * 64
    recovery = WorkflowRecoveryRepository(repository.database_path)

    with pytest.raises(WorkflowRecoveryError, match="reservation changed"):
        recovery.create_run(
            digest,
            [{"step_number": 1, "kind": "provider_selection", "name": "provider_selection"}],
            task=TaskRecord(task_type="agent.workflow", description="test workflow"),
            owner_user_id="user-1",
            submission=("user-1", "/agent/workflows", "missing-key", digest),
        )

    connection = sqlite3.connect(repository.database_path)
    workflows = connection.execute(
        "SELECT COUNT(*) FROM workflow_runs WHERE request_digest = ?", (digest,)
    ).fetchone()[0]
    tasks = connection.execute(
        "SELECT COUNT(*) FROM tasks WHERE task_type = 'agent.workflow'"
    ).fetchone()[0]
    connection.close()
    assert workflows == 0
    assert tasks == 0


def test_stale_unbound_reservation_is_failed_instead_of_staying_stuck(tmp_path):
    repository = make_repository(tmp_path)
    repository.reserve("user-1", "/agent/workflows", "stale-key", "digest-stale")
    connection = sqlite3.connect(repository.database_path)
    connection.execute(
        "UPDATE workflow_submission_keys SET updated_at = ? WHERE idempotency_key = ?",
        ("2020-01-01T00:00:00+00:00", "stale-key"),
    )
    connection.commit()
    connection.close()

    recovered = repository.reserve(
        "user-1", "/agent/workflows", "stale-key", "digest-stale"
    )

    assert recovered["state"] == "failed"
    assert recovered["created"] is False
    with pytest.raises(SubmissionStateError, match="Only a reserved"):
        repository.bind(
            "user-1", "/agent/workflows", "stale-key", "digest-stale", "workflow-1", "task-1"
        )
