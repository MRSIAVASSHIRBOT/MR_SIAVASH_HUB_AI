from uuid import UUID

import pytest
from pydantic import BaseModel

from client_helpers import authenticated_client, run_worker_once
from mrhub.agents.core import AgentCore, AgentPlanRequest
from mrhub.config import get_settings
from mrhub.infrastructure.database import TaskRepository
from mrhub.jobs.recovery import WorkflowRecoveryRepository
from mrhub.jobs.worker import WorkerEngine
from mrhub.tools.registry import ToolDefinition, ToolRegistry


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

    checked = client.post(
        f"/agent/workflows/{workflow_id}/resume-check",
        json={"request": request},
    )
    assert checked.status_code == 200
    assert checked.json()["decision"] == "resume"
    assert checked.json()["next_step_id"] == "step-2"

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
    assert result["result"]["evaluation_scope"] == "tool_execution_only"
    assert result["result"]["evaluation"]["decision"] == "accept"
    assert result["result"]["evaluation"]["passed"] == 1


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

    from mrhub.jobs.recovery import WorkflowRecoveryRepository

    original_finish = WorkflowRecoveryRepository.finish_run

    def interrupt_before_finalize(self, current_workflow_id, status, **kwargs):
        if status == "succeeded":
            raise RuntimeError("simulated crash after final checkpoint")
        return original_finish(self, current_workflow_id, status, **kwargs)

    monkeypatch.setattr(WorkflowRecoveryRepository, "finish_run", interrupt_before_finalize)
    with pytest.raises(RuntimeError, match="Workflow execution stopped"):
        run_worker_once()
    monkeypatch.setattr(WorkflowRecoveryRepository, "finish_run", original_finish)

    workflow = client.get(f"/agent/workflows/{workflow_id}").json()
    assert workflow["status"] == "paused"
    assert all(step["status"] == "succeeded" for step in workflow["steps"])

    repository = TaskRepository(get_settings().database_path)
    repository.initialize()
    task = repository.get(UUID(workflow["task_id"]))
    assert task is not None and task.status.value == "waiting_approval"

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
    assert result["result"]["evaluation_scope"] == "tool_execution_only"
    assert result["result"]["evaluation"]["decision"] == "accept"
    assert result["result"]["evaluation"]["passed"] == 1

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



def test_resume_rechecks_the_live_owner_grant_before_requeueing(monkeypatch):
    client = authenticated_client()
    calls = []

    class EmptyInput(BaseModel):
        pass

    class ReadOutput(BaseModel):
        accepted: bool

    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="cloudflare.test_read",
            description="Read one test resource through an owner grant.",
            input_model=EmptyInput,
            output_model=ReadOutput,
            handler=lambda _payload: calls.append("read") or {"accepted": True},
            required_permissions=frozenset({"cloudflare.read"}),
        )
    )
    monkeypatch.setattr(
        "mrhub.api.routes.agent.build_tool_registry",
        lambda: registry,
    )
    monkeypatch.setattr(
        "mrhub.jobs.workflow_dispatch.build_tool_registry",
        lambda: registry,
    )

    granted = client.put(
        "/tools/grants/cloudflare.read",
        json={"expires_in_seconds": 600},
    )
    assert granted.status_code == 200
    request = {
        "goal": "Resume only while the owner grant remains active",
        "tools": [{"name": "cloudflare.test_read", "payload": {}}],
    }
    created = client.post("/agent/workflows", json=request)
    assert created.status_code == 200 and created.json()["queued"] is True
    _interrupt_after_safe_step(monkeypatch)

    workflow_id = created.json()["workflow"]["workflow_id"]
    repository, _workflow_id, task_id = _workflow_and_task(client)
    stored = WorkflowRecoveryRepository(repository.database_path).get_run(
        UUID(workflow_id),
        owner_user_id="local-owner",
    )
    assert stored is not None and stored["status"] == "paused"
    assert repository.get(UUID(task_id)).status.value == "waiting_approval"

    revoked = client.delete("/tools/grants/cloudflare.read")
    assert revoked.status_code == 204
    response = client.post(
        f"/agent/workflows/{workflow_id}/resume",
        json={"request": request},
    )

    assert response.status_code == 409
    assert calls == []
    after = WorkflowRecoveryRepository(repository.database_path).get_run(
        UUID(workflow_id),
        owner_user_id="local-owner",
    )
    assert after is not None and after["status"] == "paused"


def test_resume_uses_stable_step_identity_after_request_reordering(monkeypatch):
    from mrhub.agents.workflow_runner import AgentWorkflowRunner

    client = authenticated_client()
    original_request = {
        "goal": "Resume by stable identity after harmless request reordering",
        "tools": [
            {
                "name": "text.echo",
                "payload": {"text": "alpha"},
                "step_id": "alpha",
                "depends_on": [],
            },
            {
                "name": "text.echo",
                "payload": {"text": "beta"},
                "step_id": "beta",
                "depends_on": [],
            },
        ],
    }
    created = client.post("/agent/workflows", json=original_request)
    assert created.status_code == 200
    workflow_id = created.json()["workflow"]["workflow_id"]

    original_execute = AgentCore.execute

    def checkpoint_first_step_then_interrupt(self, agent_request, **callbacks):
        callbacks["on_step"](2, "running", None)
        callbacks["on_step_result"](2, "f" * 64)
        raise RuntimeError("simulated interruption after alpha checkpoint")

    monkeypatch.setattr(AgentCore, "execute", checkpoint_first_step_then_interrupt)
    with pytest.raises(RuntimeError, match="Workflow execution stopped"):
        run_worker_once()
    monkeypatch.setattr(AgentCore, "execute", original_execute)

    stored = client.get(f"/agent/workflows/{workflow_id}").json()
    assert stored["status"] == "paused"
    stored_steps = {step["step_key"]: step for step in stored["steps"]}
    assert stored_steps["alpha"]["status"] == "succeeded"
    assert stored_steps["beta"]["status"] == "pending"

    reordered_request = {
        **original_request,
        "tools": list(reversed(original_request["tools"])),
    }
    assert AgentWorkflowRunner.request_digest(
        AgentPlanRequest.model_validate(original_request)
    ) == AgentWorkflowRunner.request_digest(
        AgentPlanRequest.model_validate(reordered_request)
    )

    checked = client.post(
        f"/agent/workflows/{workflow_id}/resume-check",
        json={"request": reordered_request},
    )
    assert checked.status_code == 200, checked.json()
    assert checked.json()["decision"] == "resume"
    assert checked.json()["next_step_id"] == "beta"

    resumed = client.post(
        f"/agent/workflows/{workflow_id}/resume",
        json={"request": reordered_request},
    )
    assert resumed.status_code == 200, resumed.json()
    assert resumed.json()["queued"] is True

    observed = {}

    def execute_and_capture_skips(self, agent_request, **callbacks):
        observed["skip_step_ids"] = set(callbacks.get("skip_step_ids", set()))
        return original_execute(self, agent_request, **callbacks)

    monkeypatch.setattr(AgentCore, "execute", execute_and_capture_skips)
    completed = run_worker_once()

    assert completed is not None and completed.status.value == "succeeded"
    assert observed["skip_step_ids"] >= {"step-1", "alpha"}
    final = client.get(f"/agent/workflows/{workflow_id}").json()
    assert final["status"] == "succeeded"
    final_steps = {step["step_key"]: step for step in final["steps"]}
    assert final_steps["alpha"]["attempt_count"] == 1
    assert final_steps["beta"]["status"] == "succeeded"

    repository = TaskRepository(get_settings().database_path)
    result = WorkerEngine(repository).get_result(UUID(final["task_id"]))
    assert result is not None
    assert result["result"]["execution_completed"] is True
    assert result["result"]["executed_tool_count"] == 1
