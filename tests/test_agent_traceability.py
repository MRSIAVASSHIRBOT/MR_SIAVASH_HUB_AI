from pathlib import Path
from uuid import UUID

from client_helpers import authenticated_client
from mrhub.agents.workflow_runner import AgentWorkflowRunner
from mrhub.config import get_settings
from mrhub.infrastructure.database import TaskRepository


def test_task_trace_is_server_generated_and_visible_to_owning_user():
    client = authenticated_client()
    response = client.post(
        "/tasks",
        json={
            "task_type": "demo.echo",
            "description": "traceability contract test",
        },
    )

    assert response.status_code == 201
    task_id = response.json()["task_id"]
    assert response.headers["x-trace-id"] == task_id

    trace = client.get(f"/agent/traces/{task_id}")
    assert trace.status_code == 200
    body = trace.json()
    assert body["trace_id"] == task_id
    assert body["task_id"] == task_id
    assert body["workflow_id"] is None
    assert body["events"][0]["event_type"] == "task.submitted"
    assert body["events"][0]["metadata"]["trace_id"] == task_id


def test_task_trace_is_not_visible_to_another_owner():
    client = authenticated_client()
    response = client.post(
        "/tasks",
        json={"task_type": "demo.echo", "description": "owner trace isolation"},
    )
    assert response.status_code == 201
    trace_id = UUID(response.json()["task_id"])

    repository = TaskRepository(get_settings().database_path)
    repository.initialize()
    repository.create_auth_user(
        "trace-other-owner",
        "trace-other-owner",
        "test-salt",
        "test-password-hash",
    )
    assert repository.get_owned_task_trace(trace_id, "trace-other-owner") is None


def test_workflow_trace_event_metadata_is_allow_listed_and_non_intrusive(tmp_path):
    repository = TaskRepository(tmp_path / "trace-events.sqlite3")
    repository.initialize()
    task_id = "12345678-1234-5678-1234-567812345678"
    workflow_id = UUID("22345678-1234-5678-1234-567812345678")
    runner = object.__new__(AgentWorkflowRunner)
    runner.repository = repository

    runner._record_trace_event(
        task_id=task_id,
        workflow_id=workflow_id,
        trace_id=task_id,
        event_type="agent.workflow.step.succeeded",
        outcome="succeeded",
        step_id="write-result",
        attempt_id="32345678-1234-5678-1234-567812345678",
        attempt_number=1,
        tool_name="text.echo",
        reason_code="verified",
    )

    events = repository.list_task_audit_events(UUID(task_id))
    assert len(events) == 1
    metadata = events[0]["metadata"]
    assert metadata == {
        "attempt_id": "32345678-1234-5678-1234-567812345678",
        "attempt_number": 1,
        "reason_code": "verified",
        "status": "succeeded",
        "step_id": "write-result",
        "tool_name": "text.echo",
        "trace_id": task_id,
        "workflow_id": str(workflow_id),
    }



def test_trace_cursor_normalizes_equivalent_timezone_offsets():
    from datetime import datetime, timedelta, timezone

    client = authenticated_client()
    submitted = client.post(
        "/tasks",
        json={"task_type": "demo.echo", "description": "trace cursor canonicalization"},
    )
    assert submitted.status_code == 201
    task_id = submitted.json()["task_id"]

    first_page = client.get(f"/agent/traces/{task_id}")
    assert first_page.status_code == 200
    event = first_page.json()["events"][0]
    stored_time = datetime.fromisoformat(event["created_at"])
    equivalent_offset = stored_time.astimezone(
        timezone(timedelta(hours=3))
    ).isoformat()

    page = client.get(
        f"/agent/traces/{task_id}",
        params={
            "before_created_at": equivalent_offset,
            "before_event_id": event["event_id"],
        },
    )

    assert page.status_code == 200
    assert page.json()["events"] == []
    assert page.json()["has_more"] is False


def test_workflow_dashboard_exposes_the_owner_scoped_execution_trace_timeline():
    web_root = Path(__file__).resolve().parents[1] / "backend" / "mrhub" / "web"
    app = (web_root / "app.js").read_text(encoding="utf-8")
    css = (web_root / "app.css").read_text(encoding="utf-8")

    assert 'actionButton("Timeline اجرا"' in app
    assert '"/agent/traces/" + encodeURIComponent(taskId)' in app
    assert 'params.set("before_created_at", cursor.before_created_at)' in app
    assert 'params.set("before_event_id", cursor.before_event_id)' in app
    assert 'element("strong", record.event_type || "رویداد نامشخص")' in app
    assert 'metadata.step_id' in app
    assert 'metadata.attempt_number' in app
    assert 'metadata.tool_name' in app
    assert 'metadata.reason_code' in app
    assert 'classList.add("workflow-trace-more")' in app
    assert ".workflow-trace-panel" in css
    assert ".workflow-trace-event" in css
    assert "innerHTML" not in app


def test_workflow_dashboard_does_not_offer_trace_lookup_without_a_valid_task_id():
    web_root = Path(__file__).resolve().parents[1] / "backend" / "mrhub" / "web"
    app = (web_root / "app.js").read_text(encoding="utf-8")
    start = app.index("  function renderWorkflowCard(workflow) {")
    end = app.index("\n  function readResumeInput()", start)
    card = app[start:end]

    assert 'typeof workflow.task_id === "string"' in card
    assert 'test(workflow.task_id)' in card
    assert 'appendWorkflowTracePage(workflow.task_id, panel)' in card
