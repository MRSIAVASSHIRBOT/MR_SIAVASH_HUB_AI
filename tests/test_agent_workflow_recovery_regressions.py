from uuid import UUID

import pytest

from client_helpers import authenticated_client, run_worker_once
from mrhub.agents.core import AgentCore
from mrhub.config import get_settings
from mrhub.infrastructure.database import TaskRepository
from mrhub.jobs.recovery import WorkflowRecoveryRepository
from mrhub.jobs.worker import WorkerEngine


def _workflow_and_task(client):
    repository = TaskRepository(get_settings().database_path)
    repository.initialize()
    with repository._connection() as connection:
        row = connection.execute(
            """
            SELECT workflow_id, task_id
            FROM workflow_runs
            ORDER BY created_at DESC
            LIMIT 1
            """
        ).fetchone()
    assert row is not None
    return repository, row["workflow_id"], row["task_id"]


def _interrupt_after_safe_step(monkeypatch):
    def interrupt_during_safe_tool(self, agent_request, **callbacks):
        callbacks["on_step"](2, "running", None)
        raise RuntimeError("simulated interruption")

    original_execute = AgentCore.execute
    monkeypatch.setattr(AgentCore, "execute", interrupt_during_safe_tool)
    with pytest.raises(RuntimeError, match="Workflow execution stopped"):
        run_worker_once()
    monkeypatch.setattr(AgentCore, "execute", original_execute)


def test_safe_interruption_resume_is_queued_then_completed_by_worker(monkeypatch):
    client = authenticated_client()
    request = {
        "goal": "Recover after a safe tool interruption",
        "tools": [{"name": "text.echo", "payload": {"text": "resume-safe"}}],
    }
    created = client.post("/agent/workflows", json=request)
    assert created.status_code == 200
    _interrupt_after_safe_step(monkeypatch)

    repository, workflow_id, task_id = _workflow_and_task(client)
    recovery = WorkflowRecoveryRepository(repository.database_path)
    stored = recovery.get_run(UUID(workflow_id), owner_user_id="local-owner")
    assert stored is not None
    assert stored["status"] == "paused"
    assert stored["steps"][1]["status"] == "retry_wait"
    task = repository.get(UUID(task_id))
    assert task is not None and task.status.value == "waiting_approval"

    resumed = client.post(
        f"/agent/workflows/{workflow_id}/resume",
        json={"request": request},
    )
    assert resumed.status_code == 200
    assert resumed.json()["queued"] is True
    assert resumed.json()["execution"] is None
    assert resumed.json()["workflow"]["status"] == "paused"
    queued_task = repository.get(UUID(task_id))
    assert queued_task is not None and queued_task.status.value == "queued"

    completed = run_worker_once()
    assert completed is not None and completed.status.value == "succeeded"
    final_workflow = client.get(f"/agent/workflows/{workflow_id}").json()
    assert final_workflow["status"] == "succeeded"
    result = WorkerEngine(repository).get_result(UUID(task_id))
    assert result is not None
    assert result["result"]["execution_completed"] is True
    assert result["result"]["executed_tool_count"] == 1


def test_finish_decision_finalizes_without_replaying_succeeded_steps(monkeypatch):
    client = authenticated_client()
    request = {
        "goal": "Finalize after the final checkpoint",
        "tools": [{"name": "text.echo", "payload": {"text": "already-done"}}],
    }
    created = client.post("/agent/workflows", json=request)
    assert created.status_code == 200
    workflow = created.json()["workflow"]
    workflow_id = workflow["workflow_id"]
    assert run_worker_once() is not None
    workflow = client.get(f"/agent/workflows/{workflow_id}").json()

    repository = TaskRepository(get_settings().database_path)
    repository.initialize()
    with repository._connection() as connection:
        connection.execute(
            "UPDATE workflow_runs SET status = 'paused' WHERE workflow_id = ?",
            (workflow_id,),
        )
        connection.execute(
            "UPDATE tasks SET status = 'waiting_approval' WHERE task_id = ?",
            (workflow["task_id"],),
        )

    def must_not_replay(self, agent_request, **callbacks):
        raise AssertionError("A fully checkpointed workflow must not invoke tools again")

    monkeypatch.setattr(AgentCore, "execute", must_not_replay)
    resumed = client.post(
        f"/agent/workflows/{workflow_id}/resume",
        json={"request": request},
    )
    assert resumed.status_code == 200
    assert resumed.json()["queued"] is True
    assert resumed.json()["execution"] is None

    completed = run_worker_once()
    assert completed is not None and completed.status.value == "succeeded"
    final_workflow = client.get(f"/agent/workflows/{workflow_id}").json()
    assert final_workflow["status"] == "succeeded"
    result = WorkerEngine(repository).get_result(UUID(workflow["task_id"]))
    assert result is not None
    assert result["result"]["execution_completed"] is True
    assert result["result"]["executed_tool_count"] == 0

    task = repository.get(UUID(workflow["task_id"]))
    assert task is not None and task.status.value == "succeeded"


def test_queued_resume_can_be_cancelled_before_worker_claim(monkeypatch):
    client = authenticated_client()
    request = {
        "goal": "Cancel a queued recovery resume",
        "tools": [{"name": "text.echo", "payload": {"text": "do-not-resume"}}],
    }
    assert client.post("/agent/workflows", json=request).status_code == 200
    _interrupt_after_safe_step(monkeypatch)
    _repository, workflow_id, task_id = _workflow_and_task(client)

    queued = client.post(
        f"/agent/workflows/{workflow_id}/resume",
        json={"request": request},
    )
    assert queued.status_code == 200 and queued.json()["queued"] is True

    cancelled = client.post(f"/agent/workflows/{workflow_id}/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    assert run_worker_once() is None

    workflow = client.get(f"/agent/workflows/{workflow_id}").json()
    assert workflow["status"] == "cancelled"
    task = _repository.get(UUID(task_id))
    assert task is not None and task.status.value == "cancelled"


def test_cancellation_during_worker_owned_resume_wins_over_success(monkeypatch):
    client = authenticated_client()
    request = {
        "goal": "Cancel while a resumed workflow is running",
        "tools": [{"name": "text.echo", "payload": {"text": "resume-cancel"}}],
    }
    assert client.post("/agent/workflows", json=request).status_code == 200
    _interrupt_after_safe_step(monkeypatch)
    repository, workflow_id, task_id = _workflow_and_task(client)

    queued = client.post(
        f"/agent/workflows/{workflow_id}/resume",
        json={"request": request},
    )
    assert queued.status_code == 200 and queued.json()["queued"] is True

    def report_success_after_cancellation(self, agent_request, **callbacks):
        callbacks["on_step"](2, "running", None)
        callbacks["on_step_result"](2, "e" * 64)
        cancelled = client.post(f"/agent/workflows/{workflow_id}/cancel")
        assert cancelled.status_code == 200
        assert cancelled.json()["status"] == "cancellation_requested"
        return {
            "execution_completed": True,
            "model_inference_started": False,
            "tools_executed": True,
            "error_code": None,
            "results": [{"ok": True}],
        }

    monkeypatch.setattr(AgentCore, "execute", report_success_after_cancellation)
    completed = run_worker_once()
    assert completed is not None and completed.status.value == "cancelled"

    workflow = client.get(f"/agent/workflows/{workflow_id}").json()
    assert workflow["status"] == "cancelled"
    task = repository.get(UUID(task_id))
    assert task is not None and task.status.value == "cancelled"
    result = WorkerEngine(repository).get_result(UUID(task_id))
    assert result is not None
    assert result["error_code"] == "cancelled_during_execution"
