"""API-level tests for owner-scoped workflow submission idempotency."""

from client_helpers import authenticated_client


def _payload(goal: str = "Idempotent workflow API test") -> dict[str, object]:
    return {
        "goal": goal,
        "tools": [{"name": "text.echo", "payload": {"text": "hello"}}],
    }


def test_workflow_submission_replay_returns_same_workflow_without_reexecution():
    client = authenticated_client()
    headers = {"Idempotency-Key": "workflow-api-replay-001"}

    first = client.post("/agent/workflows", json=_payload(), headers=headers)
    assert first.status_code == 200
    first_body = first.json()
    assert first_body["execution"]["execution_completed"] is True

    replay = client.post("/agent/workflows", json=_payload(), headers=headers)
    assert replay.status_code == 200
    replay_body = replay.json()

    assert replay_body["idempotent_replay"] is True
    assert replay_body["execution"] is None
    assert replay_body["workflow"]["workflow_id"] == first_body["workflow"]["workflow_id"]
    assert replay_body["workflow"]["task_id"] == first_body["workflow"]["task_id"]


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


def test_workflow_submission_without_idempotency_key_preserves_legacy_behavior():
    client = authenticated_client()
    response = client.post("/agent/workflows", json=_payload("legacy request"))

    assert response.status_code == 200
    body = response.json()
    assert body["execution"]["execution_completed"] is True
    assert "idempotent_replay" not in body
