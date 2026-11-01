"""API-level tests for owner-scoped queued workflow submission idempotency."""

from client_helpers import authenticated_client
from mrhub.config import get_settings
from mrhub.domain.tasks import TaskStatus
from mrhub.infrastructure.database import TaskRepository
from mrhub.jobs.worker import WorkerEngine


def _payload(goal: str = "Idempotent workflow API test") -> dict[str, object]:
    return {
        "goal": goal,
        "tools": [{"name": "text.echo", "payload": {"text": "hello"}}],
    }


def _run_one_queued_workflow():
    settings = get_settings()
    worker = WorkerEngine(TaskRepository(settings.database_path))
    return worker.run_once()


def test_workflow_submission_replay_returns_same_queued_workflow_without_reexecution():
    client = authenticated_client()
    headers = {"Idempotency-Key": "workflow-api-replay-001"}

    first = client.post("/agent/workflows", json=_payload(), headers=headers)
    assert first.status_code == 200
    first_body = first.json()
    assert first_body["execution"] is None
    assert first_body["queue"]["status"] == "queued"
    workflow_id = first_body["workflow"]["workflow_id"]
    task_id = first_body["workflow"]["task_id"]
    assert first_body["workflow"]["status"] == "queued"

    completed = _run_one_queued_workflow()
    assert completed is not None and completed.status is TaskStatus.SUCCEEDED

    replay = client.post("/agent/workflows", json=_payload(), headers=headers)
    assert replay.status_code == 200
    replay_body = replay.json()

    assert replay_body["idempotent_replay"] is True
    assert replay_body["execution"] is None
    assert replay_body["workflow"]["workflow_id"] == workflow_id
    assert replay_body["workflow"]["task_id"] == task_id
    assert replay_body["workflow"]["status"] == "succeeded"


def test_workflow_submission_rejects_same_key_with_different_request():
    client = authenticated_client()
    headers = {"Idempotency-Key": "workflow-api-conflict-001"}

    first = client.post("/agent/workflows", json=_payload("first goal"), headers=headers)
    assert first.status_code == 200

    conflicting = client.post(
        "/agent/workflows", json=_payload("different goal"), headers=headers
    )
    assert conflicting.status_code == 409
    assert "different request" in conflicting.json()["detail"]


def test_workflow_submission_returns_before_worker_execution():
    client = authenticated_client()
    response = client.post("/agent/workflows", json=_payload("queued request"))

    assert response.status_code == 200
    body = response.json()
    assert body["execution"] is None
    assert body["workflow"]["status"] == "queued"
    assert body["queue"]["worker_dispatch"] == "pending"

    completed = _run_one_queued_workflow()
    assert completed is not None and completed.status is TaskStatus.SUCCEEDED

    final = client.get(f"/agent/workflows/{body['workflow']['workflow_id']}")
    assert final.status_code == 200
    assert final.json()["status"] == "succeeded"
