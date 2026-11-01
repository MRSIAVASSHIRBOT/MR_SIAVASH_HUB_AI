import sqlite3
from datetime import UTC, datetime, timedelta

import pytest
from cryptography.fernet import Fernet

from mrhub.agents.execution_inputs import (
    ExecutionInputError,
    ExecutionInputUnavailable,
    ExecutionInputValidationError,
    WorkflowExecutionInputRepository,
)
from mrhub.domain.tasks import TaskRecord
from mrhub.infrastructure.database import TaskRepository
from mrhub.jobs.recovery import WorkflowRecoveryRepository


def setup_repo(tmp_path):
    database_path = tmp_path / "inputs.sqlite3"
    TaskRepository(database_path).initialize()
    recovery = WorkflowRecoveryRepository(database_path)
    connection = sqlite3.connect(database_path)
    connection.execute(
        """INSERT INTO auth_users
           (user_id, username, salt, password_hash, created_at)
           VALUES (?, ?, ?, ?, ?)""",
        ("owner-1", "owner1", "salt", "hash", datetime.now(UTC).isoformat()),
    )
    connection.commit()
    connection.close()
    workflow_id = recovery.create_run(
        "a" * 64,
        [{"step_number": 1, "kind": "provider_selection", "name": "provider_selection"}],
        task=TaskRecord(task_type="agent.workflow", description="test"),
        owner_user_id="owner-1",
    )
    return database_path, str(workflow_id)


def test_encrypted_payload_round_trips_for_owner_only(tmp_path):
    key = Fernet.generate_key().decode("ascii")
    database_path, workflow_id = setup_repo(tmp_path)
    repo = WorkflowExecutionInputRepository(database_path, key)
    payload = {
        "goal": "test workflow",
        "tools": [{"name": "text.echo", "payload": {"text": "hello"}}],
    }

    metadata = repo.store(workflow_id, "owner-1", payload)

    assert metadata["payload_digest"]
    assert repo.load(workflow_id, "owner-1") == payload
    with pytest.raises(LookupError):
        repo.load(workflow_id, "owner-2")


def test_missing_key_fails_closed_without_creating_plaintext(tmp_path):
    database_path, workflow_id = setup_repo(tmp_path)
    repo = WorkflowExecutionInputRepository(database_path, None)

    with pytest.raises(ExecutionInputUnavailable, match="refusing plaintext"):
        repo.store(workflow_id, "owner-1", {"goal": "private"})
    with pytest.raises(ExecutionInputUnavailable, match="not configured"):
        repo.load(workflow_id, "owner-1")


def test_duplicate_store_does_not_overwrite_existing_payload(tmp_path):
    key = Fernet.generate_key().decode("ascii")
    database_path, workflow_id = setup_repo(tmp_path)
    repo = WorkflowExecutionInputRepository(database_path, key)
    repo.store(workflow_id, "owner-1", {"goal": "original"})

    with pytest.raises(ExecutionInputError, match="already exists"):
        repo.store(workflow_id, "owner-1", {"goal": "replacement"})
    assert repo.load(workflow_id, "owner-1") == {"goal": "original"}


@pytest.mark.parametrize(
    "payload",
    [
        {"api_key": "not-allowed"},
        {"nested": {"authorization": "not-allowed"}},
        {"tools": [{"client_secret": "not-allowed"}]},
    ],
)
def test_sensitive_looking_fields_are_rejected(tmp_path, payload):
    key = Fernet.generate_key().decode("ascii")
    database_path, workflow_id = setup_repo(tmp_path)
    repo = WorkflowExecutionInputRepository(database_path, key)

    with pytest.raises(ExecutionInputValidationError, match="Sensitive-looking"):
        repo.store(workflow_id, "owner-1", payload)


def test_payload_size_is_bounded(tmp_path):
    key = Fernet.generate_key().decode("ascii")
    database_path, workflow_id = setup_repo(tmp_path)
    repo = WorkflowExecutionInputRepository(database_path, key)

    with pytest.raises(ExecutionInputValidationError, match="64 KiB"):
        repo.store(workflow_id, "owner-1", {"text": "x" * (64 * 1024)})


def test_expired_payload_is_not_returned(tmp_path):
    key = Fernet.generate_key().decode("ascii")
    database_path, workflow_id = setup_repo(tmp_path)
    repo = WorkflowExecutionInputRepository(database_path, key)
    expiry = (datetime.now(UTC) - timedelta(minutes=1)).isoformat()
    repo.store(workflow_id, "owner-1", {"goal": "expired"}, expires_at=expiry)

    with pytest.raises(ExecutionInputUnavailable, match="expired"):
        repo.load(workflow_id, "owner-1")
