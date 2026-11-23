from client_helpers import authenticated_client, run_worker_once
from mrhub.config import get_settings
from mrhub.memory.repository import MemoryRepository


def _completed_workflow(client):
    submitted = client.post(
        "/agent/workflows",
        json={
            "goal": "Create a durable workflow for the lesson preview integration test",
            "tools": [{"name": "text.echo", "payload": {"text": "verified output"}}],
        },
    )
    assert submitted.status_code == 200
    workflow_id = submitted.json()["workflow"]["workflow_id"]
    run_worker_once()
    history = client.get(f"/agent/workflows/{workflow_id}")
    assert history.status_code == 200
    assert history.json()["status"] == "succeeded"
    return workflow_id, history.json()


def test_lesson_preview_uses_persisted_success_digest_and_never_writes_memory():
    client = authenticated_client()
    workflow_id, workflow = _completed_workflow(client)
    step = next(item for item in workflow["steps"] if item["status"] == "succeeded")
    output_digest = step["output_digest"]
    assert len(output_digest) == 64

    memory = MemoryRepository(get_settings().database_path)
    before = memory.list_entries("local-owner", limit=100)

    lesson_text = "Keep validated dependency ordering before any external tool step."
    response = client.post(
        f"/agent/workflows/{workflow_id}/lessons/preview",
        json={
            "step_id": step["step_key"],
            "category": "engineering",
            "lesson_text": lesson_text,
        },
    )

    assert response.status_code == 200
    proposal = response.json()["proposal"]
    assert proposal["evidence_digest"] == output_digest
    assert proposal["owner_review_required"] is True
    assert proposal["automatic_memory_write"] is False
    assert proposal["execution_authorized"] is False
    assert proposal["memory_entry_preview"]["content"] == lesson_text
    assert proposal["memory_entry_preview"]["memory_type"] == "procedural"

    after = memory.list_entries("local-owner", limit=100)
    assert after == before

    audit_events = memory.tasks.list_audit()
    event = next(
        item for item in reversed(audit_events)
        if item["event_type"] == "agent.lesson_previewed"
    )
    assert event["actor_id"] == "local-owner"
    assert lesson_text not in str(event["metadata"])


def test_lesson_preview_rejects_sensitive_text_and_invalid_step():
    client = authenticated_client()
    workflow_id, workflow = _completed_workflow(client)
    step = next(item for item in workflow["steps"] if item["status"] == "succeeded")

    sensitive = client.post(
        f"/agent/workflows/{workflow_id}/lessons/preview",
        json={
            "step_id": step["step_key"],
            "category": "engineering",
            "lesson_text": "password=not-a-real-secret; do not retain this note",
        },
    )
    assert sensitive.status_code == 422

    unknown = client.post(
        f"/agent/workflows/{workflow_id}/lessons/preview",
        json={
            "step_id": "missing-step",
            "category": "engineering",
            "lesson_text": "Keep validated dependency ordering before external steps.",
        },
    )
    assert unknown.status_code == 404


def test_lesson_preview_requires_authentication(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from mrhub.main import create_app

    monkeypatch.setenv("MRH_DATABASE_PATH", str(tmp_path / "lesson-auth.sqlite3"))
    get_settings.cache_clear()
    response = TestClient(create_app()).post(
        "/agent/workflows/12345678-1234-5678-1234-567812345678/lessons/preview",
        json={
            "step_id": "step-one",
            "category": "engineering",
            "lesson_text": "Keep verified evidence attached to every reusable lesson.",
        },
    )
    assert response.status_code in (401, 403)
    get_settings.cache_clear()
