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
    assert workflow["stored_tool_payloads"] is False
    assert body["execution"]["execution_completed"] is True

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


def test_agent_workflow_not_found():
    client = authenticated_client()
    response = client.get(
        "/agent/workflows/00000000-0000-0000-0000-000000000002"
    )
    assert response.status_code == 404
