from uuid import UUID

import pytest

from mrhub.agents.workflow_repository import AgentWorkflowRepository


def test_workflow_persists_step_transitions_without_payloads(tmp_path):
    repository = AgentWorkflowRepository(tmp_path / "workflow.sqlite3")
    workflow = repository.create(
        "a" * 64,
        {
            "execution_ready": True,
            "steps": [
                {"step": 1, "kind": "provider_selection", "status": "selected"},
                {"step": 2, "kind": "tool", "name": "text.echo", "status": "ready"},
            ],
        },
    )
    workflow_id = UUID(workflow["workflow_id"])
    repository.start(workflow_id)
    repository.record_step(workflow_id, 2, "running")
    repository.record_step(workflow_id, 2, "succeeded")
    repository.finish(workflow_id, "succeeded")

    restored = repository.get(workflow_id)
    assert restored["status"] == "succeeded"
    assert restored["steps"][1]["status"] == "succeeded"
    assert restored["stored_request"] is False
    assert restored["stored_tool_payloads"] is False
    assert restored["stored_tool_outputs"] is False


def test_workflow_rejects_invalid_state_transition(tmp_path):
    repository = AgentWorkflowRepository(tmp_path / "workflow.sqlite3")
    workflow = repository.create("b" * 64, {"execution_ready": True, "steps": []})
    with pytest.raises(RuntimeError):
        repository.finish(UUID(workflow["workflow_id"]), "succeeded")


def test_blocked_workflow_cannot_be_started(tmp_path):
    repository = AgentWorkflowRepository(tmp_path / "workflow.sqlite3")
    workflow = repository.create("c" * 64, {"execution_ready": False, "steps": []})
    assert workflow["status"] == "blocked"
    with pytest.raises(RuntimeError):
        repository.start(UUID(workflow["workflow_id"]))
