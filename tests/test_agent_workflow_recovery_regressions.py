from threading import Event, Thread
from uuid import UUID

from client_helpers import authenticated_client
from mrhub.agents.core import AgentCore
from mrhub.config import get_settings
from mrhub.infrastructure.database import TaskRepository
from mrhub.jobs.worker import WorkerEngine


def _run_worker_once():
    return WorkerEngine(TaskRepository(get_settings().database_path)).run_once()


def _workflow_and_task(client):
    repository = TaskRepository(get_settings().database_path)
    repository.initialize()
    with repository._connection() as connection:
        row = connection.execute(
            """SELECT workflow_id, task_id FROM workflow_runs ORDER BY created_at DESC LIMIT 1"""
        ).fetchone()
    assert row is not None
    return repository, row["workflow_id"], row["task_id"]


def test_safe_interruption_keeps_job_resumable_and_resume_completes(monkeypatch):
    client = authenticated_client()
    request = {
        "goal": "Recover after a safe tool interruption",
        "tools": [{"name": "text.echo", "payload": {"text": "resume-safe"}}],
    }

    def interrupt_during_safe_tool(self, agent_request, **callbacks):
        callbacks["on_step"](2, "running", None)
        raise RuntimeError("simulated interruption")

    original_execute = AgentCore.execute
    monkeypatch.setattr(AgentCore, "execute", interrupt_during_safe_tool)
    submitted = client.post("/agent/workflows", json=request)
    assert submitted.status_code == 200
    claimed = _run_worker_once()
    assert claimed is not None and claimed.status.value == "waiting_approval"

    repository, workflow_id, task_id = _workflow_and_task(client)
    from mrhub.jobs.recovery import WorkflowRecoveryRepository

    stored = WorkflowRecoveryRepository(repository.database_path).get_run(UUID(workflow_id))
    assert stored is not None
    assert stored["status"] == "paused"
    assert stored["steps"][1]["status"] == "retry_wait"
    task = repository.get(UUID(task_id))
    assert task is not None and task.status.value == "waiting_approval"

    monkeypatch.setattr(AgentCore, "execute", original_execute)
    resumed = client.post(
        f"/agent/workflows/{workflow_id}/resume",
        json={"request": request},
    )
    assert resumed.status_code == 200
    assert resumed.json()["workflow"]["status"] == "queued"
    completed = _run_worker_once()
    assert completed is not None and completed.status.value == "succeeded"
    final = client.get(f"/agent/workflows/{workflow_id}")
    assert final.status_code == 200 and final.json()["status"] == "succeeded"


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
    completed = _run_worker_once()
    assert completed is not None and completed.status.value == "succeeded"

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
    assert resumed.json()["workflow"]["status"] == "queued"
    completed = _run_worker_once()
    assert completed is not None and completed.status.value == "succeeded"
    final = client.get(f"/agent/workflows/{workflow_id}")
    assert final.status_code == 200
    assert final.json()["status"] == "succeeded"

    task = repository.get(UUID(workflow["task_id"]))
    assert task is not None and task.status.value == "succeeded"



def test_cancel_during_safe_step_commits_job_and_workflow_together(monkeypatch):
    client = authenticated_client()
    request = {
        "goal": "Cancel a running safe workflow",
        "tools": [{"name": "text.echo", "payload": {"text": "wait-for-cancel"}}],
    }
    submitted = client.post("/agent/workflows", json=request)
    assert submitted.status_code == 200
    workflow = submitted.json()["workflow"]
    entered = Event()
    release = Event()
    worker_result = []

    def block_safe_step(self, agent_request, **callbacks):
        callbacks["on_step"](2, "running", None)
        entered.set()
        assert release.wait(5)
        callbacks["on_step_result"](2, "0" * 64)
        return {"execution_completed": True, "results": [{"ok": True}]}

    monkeypatch.setattr(AgentCore, "execute", block_safe_step)

    def run_worker():
        worker_result.append(_run_worker_once())

    thread = Thread(target=run_worker)
    thread.start()
    assert entered.wait(5)

    requested = client.post(f"/jobs/{workflow['task_id']}/cancel")
    assert requested.status_code == 200
    assert requested.json()["status"] == "waiting_approval"
    release.set()
    thread.join(10)
    assert not thread.is_alive()

    final_task = client.get(f"/tasks/{workflow['task_id']}")
    final_workflow = client.get(f"/agent/workflows/{workflow['workflow_id']}")
    assert final_task.status_code == 200
    assert final_workflow.status_code == 200
    assert final_task.json()["status"] == "cancelled"
    assert final_workflow.json()["status"] == "cancelled"
    assert worker_result[0] is not None
    assert worker_result[0].status.value == "cancelled"
