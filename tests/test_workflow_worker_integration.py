"""End-to-end tests for queued, encrypted workflow execution."""
from uuid import UUID

from client_helpers import authenticated_client, run_worker_once
from mrhub.config import get_settings
from mrhub.infrastructure.database import TaskRepository
from mrhub.jobs.recovery import WorkflowRecoveryRepository


def test_workflow_is_queued_then_executed_by_worker_and_payload_is_deleted() -> None:
    client = authenticated_client()
    request = {
        "goal": "Run the approved deterministic echo tool",
        "tools": [{"name": "text.echo", "payload": {"text": "worker-owned"}}],
    }

    response = client.post("/agent/workflows", json=request)
    assert response.status_code == 200
    body = response.json()
    workflow = body["workflow"]
    workflow_id = UUID(workflow["workflow_id"])
    task_id = UUID(workflow["task_id"])

    # The HTTP request only enqueues durable work; it does not execute the tool.
    assert body["queued"] is True
    assert body["execution"] is None
    assert workflow["status"] == "queued"

    repository = TaskRepository(get_settings().database_path)
    repository.initialize()
    recovery = WorkflowRecoveryRepository(repository.database_path)
    encrypted = recovery.get_encrypted_payload(
        workflow_id, owner_user_id="local-owner"
    )
    assert encrypted is not None
    assert encrypted["task_id"] == str(task_id)
    assert encrypted["ciphertext_b64"]

    completed = run_worker_once()
    assert completed is not None
    assert completed.task_id == task_id
    assert completed.status.value == "succeeded"

    stored_task = repository.get(task_id)
    stored_workflow = recovery.get_run(
        workflow_id, owner_user_id="local-owner"
    )
    assert stored_task is not None and stored_task.status.value == "succeeded"
    assert stored_workflow is not None
    assert stored_workflow["status"] == "succeeded"
    assert stored_workflow["steps"][1]["status"] == "succeeded"
    assert recovery.get_encrypted_payload(
        workflow_id, owner_user_id="local-owner"
    ) is None

    worker_result = __import__(
        "mrhub.jobs.worker", fromlist=["WorkerEngine"]
    ).WorkerEngine(repository).get_result(task_id)
    assert worker_result is not None
    assert worker_result["result"]["execution_completed"] is True
    assert worker_result["result"]["executed_tool_count"] == 1


def test_workflow_payload_is_not_readable_by_another_owner() -> None:
    client = authenticated_client()
    request = {
        "goal": "Check owner isolation",
        "tools": [{"name": "text.echo", "payload": {"text": "private"}}],
    }
    response = client.post("/agent/workflows", json=request)
    assert response.status_code == 200
    workflow_id = UUID(response.json()["workflow"]["workflow_id"])

    repository = TaskRepository(get_settings().database_path)
    recovery = WorkflowRecoveryRepository(repository.database_path)
    assert recovery.get_encrypted_payload(
        workflow_id, owner_user_id="some-other-user"
    ) is None
