from fastapi.testclient import TestClient

from client_helpers import authenticated_client
from mrhub.config import get_settings
from mrhub.main import create_app


def test_agent_plan_selects_provider_and_only_plans_tools():
    client = authenticated_client()
    response = client.post(
        "/agent/plan",
        json={
            "goal": "Echo this message",
            "tools": [{"name": "text.echo", "payload": {"text": "hello"}}],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["selected_provider"]["provider"] == "stub"
    assert body["execution_ready"] is True
    assert body["decision_mode"] == "plan_only"
    assert body["model_inference_started"] is False
    assert body["tools_executed"] is False


def test_agent_plan_blocks_unregistered_tool():
    client = authenticated_client()
    response = client.post(
        "/agent/plan",
        json={
            "goal": "Try unavailable tool",
            "tools": [{"name": "shell.execute", "payload": {}}],
        },
    )
    assert response.status_code == 200
    assert response.json()["execution_ready"] is False
    assert response.json()["steps"][1]["status"] == "not_registered"


def test_agent_plan_rejects_unsupported_capabilities():
    client = authenticated_client()
    response = client.post(
        "/agent/plan", json={"goal": "Analyze an image", "requires_vision": True}
    )
    assert response.status_code == 503


def test_agent_plan_limits_number_of_tools():
    client = authenticated_client()
    response = client.post(
        "/agent/plan",
        json={
            "goal": "Too many tools",
            "tools": [{"name": "text.echo", "payload": {"text": "x"}}] * 6,
        },
    )
    assert response.status_code == 422


def test_agent_plan_requires_authentication(tmp_path, monkeypatch):
    monkeypatch.setenv("MRH_DATABASE_PATH", str(tmp_path / "test.sqlite3"))
    get_settings.cache_clear()
    response = TestClient(create_app()).post("/agent/plan", json={"goal": "plan"})
    assert response.status_code in (401, 403)
    get_settings.cache_clear()


def test_agent_execute_runs_registered_safe_tool():
    client = authenticated_client()
    response = client.post(
        "/agent/execute",
        json={
            "goal": "Echo safely",
            "tools": [{"name": "text.echo", "payload": {"text": "hello"}}],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["decision_mode"] == "controlled_tool_execution"
    assert body["execution_completed"] is True
    assert body["model_inference_started"] is False
    assert body["results"][0]["result"]["character_count"] == 5


def test_agent_execute_requires_authentication(tmp_path, monkeypatch):
    monkeypatch.setenv("MRH_DATABASE_PATH", str(tmp_path / "test.sqlite3"))
    get_settings.cache_clear()
    response = TestClient(create_app()).post(
        "/agent/execute", json={"goal": "must authenticate"}
    )
    assert response.status_code in (401, 403)
    get_settings.cache_clear()


def test_agent_execute_persists_metadata_without_prompt_or_tool_payload():
    client = authenticated_client()
    response = client.post(
        "/agent/execute",
        json={
            "goal": "PRIVATE GOAL MUST NOT BE STORED",
            "tools": [
                {
                    "name": "text.echo",
                    "payload": {"text": "PRIVATE TOOL INPUT MUST NOT BE STORED"},
                }
            ],
        },
    )
    assert response.status_code == 200
    body = response.json()
    run = body["run"]
    assert run["status"] == "succeeded"
    assert run["executed_tool_count"] == 1
    assert run["stored_payloads"] is False
    assert run["stored_tool_outputs"] is False
    assert "PRIVATE GOAL MUST NOT BE STORED" not in str(run)
    assert "PRIVATE TOOL INPUT MUST NOT BE STORED" not in str(run)

    history = client.get(f"/agent/runs/{run['run_id']}")
    assert history.status_code == 200
    assert history.json()["request_digest"] == run["request_digest"]
    assert history.json()["tool_names"] == ["text.echo"]


def test_agent_run_history_returns_not_found_for_unknown_id():
    client = authenticated_client()
    response = client.get("/agent/runs/00000000-0000-0000-0000-000000000001")
    assert response.status_code == 404


def test_agent_workflow_executes_and_persists_each_step():
    client = authenticated_client()
    response = client.post(
        "/agent/workflows",
        json={
            "goal": "Run a durable safe workflow",
            "tools": [{"name": "text.echo", "payload": {"text": "hello"}}],
        },
    )
    assert response.status_code == 200
    body = response.json()
    workflow = body["workflow"]
    assert workflow["status"] == "succeeded"
    assert workflow["steps"][1]["status"] == "succeeded"
    assert workflow["stored_request"] is False
    assert workflow["stored_step_payloads"] is False
    assert workflow["stored_step_outputs"] is False
    assert body["execution"]["execution_completed"] is True
    assert workflow["task_id"] is not None

    linked_task = client.get(f"/tasks/{workflow['task_id']}")
    assert linked_task.status_code == 200
    assert linked_task.json()["status"] == "succeeded"

    history = client.get("/agent/workflows/" + workflow["workflow_id"])
    assert history.status_code == 200
    assert history.json()["steps"][1]["status"] == "succeeded"


def test_agent_workflow_persists_blocked_plan_without_execution():
    client = authenticated_client()
    response = client.post(
        "/agent/workflows",
        json={
            "goal": "Do not execute unknown tools",
            "tools": [{"name": "shell.execute", "payload": {}}],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["workflow"]["status"] == "blocked"
    assert body["execution"] is None

    history = client.get("/agent/workflows/" + body["workflow"]["workflow_id"])
    assert history.status_code == 200
    assert history.json()["status"] == "blocked"


def test_agent_workflow_not_found():
    client = authenticated_client()
    response = client.get(
        "/agent/workflows/00000000-0000-0000-0000-000000000002"
    )
    assert response.status_code == 404



def test_workflow_request_digest_distinguishes_same_length_goals():
    from mrhub.agents.core import AgentPlanRequest
    from mrhub.api.routes.agent import _workflow_digest

    first = AgentPlanRequest(goal="alpha", tools=[{"name": "text.echo", "payload": {"text": "one"}}])
    second = AgentPlanRequest(goal="bravo", tools=[{"name": "text.echo", "payload": {"text": "one"}}])
    third = AgentPlanRequest(goal="alpha", tools=[{"name": "text.echo", "payload": {"text": "two"}}])

    assert _workflow_digest(first) != _workflow_digest(second)
    assert _workflow_digest(first) != _workflow_digest(third)



def test_workflow_resume_check_is_owner_scoped_and_never_executes():
    client = authenticated_client()
    created = client.post(
        "/agent/workflows",
        json={
            "goal": "Create resumability metadata",
            "tools": [{"name": "text.echo", "payload": {"text": "safe"}}],
        },
    )
    assert created.status_code == 200
    workflow_id = created.json()["workflow"]["workflow_id"]
    checked = client.post(
        f"/agent/workflows/{workflow_id}/resume-check",
        json={
            "request": {
                "goal": "Create resumability metadata",
                "tools": [{"name": "text.echo", "payload": {"text": "safe"}}],
            }
        },
    )
    assert checked.status_code == 200
    assert checked.json()["decision"] == "terminal"
    assert checked.json()["execution_started"] is False




def test_agent_workflow_resume_revalidates_and_executes_only_remaining_step():
    from mrhub.infrastructure.database import TaskRepository

    client = authenticated_client()
    original = {
        "goal": "Resume a safe interrupted workflow",
        "tools": [{"name": "text.echo", "payload": {"text": "resume-me"}}],
    }
    created = client.post("/agent/workflows", json=original)
    assert created.status_code == 200
    workflow = created.json()["workflow"]
    workflow_id = workflow["workflow_id"]

    repository = TaskRepository(get_settings().database_path)
    repository.initialize()
    with repository._connection() as connection:
        connection.execute(
            "UPDATE workflow_runs SET status = 'paused' WHERE workflow_id = ?",
            (workflow_id,),
        )
        connection.execute(
            """UPDATE workflow_steps
               SET status = 'retry_wait', output_digest = NULL,
                   error_code = 'worker_interrupted', finished_at = NULL
               WHERE workflow_id = ? AND step_number = 2""",
            (workflow_id,),
        )
        connection.execute(
            "UPDATE tasks SET status = 'waiting_approval' WHERE task_id = ?",
            (workflow["task_id"],),
        )

    resumed = client.post(
        f"/agent/workflows/{workflow_id}/resume",
        json={"request": original},
    )
    assert resumed.status_code == 200
    body = resumed.json()
    assert body["workflow"]["status"] == "succeeded"
    assert body["execution"]["execution_completed"] is True
    assert body["execution"]["executed_tool_count"] == 1

    task = client.get(f"/tasks/{workflow['task_id']}")
    assert task.status_code == 200
    assert task.json()["status"] == "succeeded"



def test_agent_workflow_resume_continues_only_from_interrupted_safe_step():
    from mrhub.domain.tasks import TaskRecord, TaskStatus
    from mrhub.infrastructure.database import TaskRepository
    from mrhub.jobs.engine import JobEngine
    from mrhub.jobs.leases import LeaseManager
    from mrhub.jobs.recovery import WorkflowRecoveryRepository

    client = authenticated_client()
    settings = get_settings()
    tasks = TaskRepository(settings.database_path)
    tasks.initialize()
    with tasks._connection() as connection:
        owner = connection.execute(
            "SELECT user_id FROM auth_users WHERE username = 'owner'"
        ).fetchone()["user_id"]

    request = {
        "goal": "Resume a safely interrupted workflow",
        "tools": [{"name": "text.echo", "payload": {"text": "resume-safe"}}],
    }
    from mrhub.agents.core import AgentPlanRequest

    parsed = AgentPlanRequest.model_validate(request)
    from mrhub.api.routes.agent import _workflow_digest
    from mrhub.agents.core import AgentCore
    from mrhub.api.routes.models import build_model_router
    from mrhub.tools.builtins import build_tool_registry
    from mrhub.agents.workflow_runner import AgentWorkflowRunner

    core = AgentCore(build_model_router(), build_tool_registry())
    plan = core.plan(parsed)
    task = TaskRecord(task_type="agent.workflow", description="recovery test")
    recovery = WorkflowRecoveryRepository(tasks.database_path)
    workflow_id = recovery.create_run(
        _workflow_digest(parsed),
        [
            {"step_number": 1, "kind": "provider_selection", "name": "provider_selection"},
            {"step_number": 2, "kind": "safe_tool", "name": "text.echo"},
        ],
        task=task,
        owner_user_id=owner,
    )

    jobs = JobEngine(tasks)
    jobs.transition(task.task_id, TaskStatus.RUNNING)
    leases = LeaseManager(tasks.database_path)
    lease = leases.acquire(str(task.task_id), "test-resume-worker")
    assert lease is not None
    recovery.start_run(workflow_id, lease=lease)
    provider_attempt = recovery.start_step(workflow_id, 1, lease=lease)
    recovery.complete_step(
        workflow_id,
        provider_attempt,
        AgentWorkflowRunner._digest(plan["selected_provider"]),
        lease=lease,
    )
    recovery.start_step(workflow_id, 2, lease=lease)
    recovery.mark_interrupted(workflow_id, lease=lease)
    jobs.transition(task.task_id, TaskStatus.WAITING_APPROVAL, lease=lease)
    assert leases.release(lease)

    response = client.post(
        f"/agent/workflows/{workflow_id}/resume",
        json={"request": request},
    )

    assert response.status_code == 200
    assert response.json()["workflow"]["status"] == "succeeded"
    assert response.json()["workflow"]["steps"][1]["status"] == "succeeded"
    linked_task = client.get(f"/tasks/{task.task_id}")
    assert linked_task.status_code == 200
    assert linked_task.json()["status"] == "succeeded"
