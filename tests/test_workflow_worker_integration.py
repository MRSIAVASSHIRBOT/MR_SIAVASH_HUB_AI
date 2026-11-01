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
    with repository._connection() as connection:
        owner_row = connection.execute(
            "SELECT owner_user_id FROM workflow_runs WHERE workflow_id = ?",
            (str(workflow_id),),
        ).fetchone()
    assert owner_row is not None
    owner_user_id = owner_row["owner_user_id"]
    encrypted = recovery.get_encrypted_payload(
        workflow_id, owner_user_id=owner_user_id
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
        workflow_id, owner_user_id=owner_user_id
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


def test_queued_workflow_can_be_cancelled_by_its_owner() -> None:
    client = authenticated_client()
    request = {
        "goal": "Queue a workflow and cancel it before execution",
        "tools": [{"name": "text.echo", "payload": {"text": "must-not-run"}}],
    }
    response = client.post("/agent/workflows", json=request)
    assert response.status_code == 200
    workflow = response.json()["workflow"]
    workflow_id = UUID(workflow["workflow_id"])
    task_id = UUID(workflow["task_id"])

    cancelled = client.post(f"/agent/workflows/{workflow_id}/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"

    repository = TaskRepository(get_settings().database_path)
    recovery = WorkflowRecoveryRepository(repository.database_path)
    stored_task = repository.get(task_id)
    stored_workflow = recovery.get_run(workflow_id, owner_user_id="local-owner")
    assert stored_task is not None and stored_task.status.value == "cancelled"
    assert stored_workflow is not None and stored_workflow["status"] == "cancelled"
    with repository._connection() as connection:
        payload = connection.execute(
            "SELECT 1 FROM workflow_payloads WHERE workflow_id = ?",
            (str(workflow_id),),
        ).fetchone()
    assert payload is None
    assert run_worker_once() is None


def test_workflow_idempotency_replays_the_atomically_created_resource() -> None:
    client = authenticated_client()
    request = {
        "goal": "Create an idempotent workflow",
        "tools": [{"name": "text.echo", "payload": {"text": "once"}}],
    }
    headers = {"Idempotency-Key": "workflow-atomic-replay"}
    first = client.post("/agent/workflows", json=request, headers=headers)
    second = client.post("/agent/workflows", json=request, headers=headers)

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["idempotent_replay"] is True
    assert (
        second.json()["workflow"]["workflow_id"]
        == first.json()["workflow"]["workflow_id"]
    )
