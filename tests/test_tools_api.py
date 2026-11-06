from fastapi.testclient import TestClient
from pydantic import BaseModel

from client_helpers import authenticated_client
from mrhub.api.routes import tools as tools_api
from mrhub.config import get_settings
from mrhub.domain.tasks import RiskClass
from mrhub.infrastructure.database import TaskRepository
from mrhub.main import create_app
from mrhub.tools.registry import ToolDefinition, ToolRegistry


def _audit_events():
    repository = TaskRepository(get_settings().database_path)
    repository.initialize()
    return repository.list_audit()


def test_tool_catalog_is_authenticated_and_exposes_contracts():
    client = authenticated_client()
    response = client.get("/tools")
    assert response.status_code == 200
    catalog = response.json()
    assert [item["name"] for item in catalog] == ["text.echo"]
    assert catalog[0]["input_schema"]["properties"]["text"]["maxLength"] == 500
    assert catalog[0]["external_side_effect"] is False


def test_tool_invoke_executes_only_registered_safe_tool():
    client = authenticated_client()
    response = client.post("/tools/text.echo/invoke", json={"payload": {"text": "hello"}})
    assert response.status_code == 200
    assert response.json()["tool"] == "text.echo"
    assert response.json()["result"] == {"text": "hello", "character_count": 5}
    assert response.json()["executed"] is True
    assert len(response.json()["correlation_id"]) == 36


def test_tool_invoke_rejects_unregistered_tool_and_audits_without_payload():
    client = authenticated_client()
    response = client.post(
        "/tools/shell.execute/invoke",
        json={"payload": {"command": "private-command-must-not-be-audited"}},
    )
    assert response.status_code == 404
    events = [
        event for event in _audit_events()
        if event["event_type"] == "tool.invocation"
    ]
    assert events[-1]["outcome"] == "failure"
    assert events[-1]["metadata"]["reason_code"] == "tool_not_registered"
    assert "private-command-must-not-be-audited" not in str(events)


def test_tool_invoke_validates_payload_without_echoing_input_and_audits_failure():
    client = authenticated_client()
    response = client.post(
        "/tools/text.echo/invoke",
        json={"payload": {"text": "", "secret": "private-invalid-input"}},
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "Tool input validation failed"
    assert "private-invalid-input" not in response.text
    events = [
        event for event in _audit_events()
        if event["event_type"] == "tool.invocation"
    ]
    assert events[-1]["outcome"] == "failure"
    assert events[-1]["metadata"]["reason_code"] == "tool_input_invalid"
    assert "private-invalid-input" not in str(events)


def test_tool_catalog_requires_authentication(tmp_path, monkeypatch):
    monkeypatch.setenv("MRH_DATABASE_PATH", str(tmp_path / "test.sqlite3"))
    get_settings.cache_clear()
    response = TestClient(create_app()).get("/tools")
    assert response.status_code in (401, 403)
    get_settings.cache_clear()


def test_tool_invoke_requires_authentication(tmp_path, monkeypatch):
    monkeypatch.setenv("MRH_DATABASE_PATH", str(tmp_path / "test.sqlite3"))
    get_settings.cache_clear()
    response = TestClient(create_app()).post(
        "/tools/text.echo/invoke", json={"payload": {"text": "hello"}}
    )
    assert response.status_code in (401, 403)
    get_settings.cache_clear()


def test_owner_grant_controls_protected_tool_invocation_and_is_audited(monkeypatch):
    client = authenticated_client()

    class ProtectedInput(BaseModel):
        text: str

    class ProtectedOutput(BaseModel):
        accepted: bool

    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="cloudflare.inventory",
            description="Read Cloudflare inventory metadata without modifying resources.",
            input_model=ProtectedInput,
            output_model=ProtectedOutput,
            handler=lambda _payload: ProtectedOutput(accepted=True),
            risk_class=RiskClass.LOW,
            required_permissions=frozenset({"cloudflare.read"}),
        )
    )
    monkeypatch.setattr(tools_api, "build_tool_registry", lambda: registry)

    payload = {"payload": {"text": "private-input-must-not-enter-audit"}}
    denied = client.post("/tools/cloudflare.inventory/invoke", json=payload)
    assert denied.status_code == 403
    assert denied.json()["detail"]["decision"] == "deny"

    grant = client.put(
        "/tools/grants/cloudflare.read",
        json={"expires_in_seconds": 3600},
    )
    assert grant.status_code == 200
    assert grant.json()["permission"] == "cloudflare.read"

    active = client.get("/tools/grants")
    assert active.status_code == 200
    assert active.headers["cache-control"] == "no-store"
    assert [item["permission"] for item in active.json()] == ["cloudflare.read"]

    allowed = client.post("/tools/cloudflare.inventory/invoke", json=payload)
    assert allowed.status_code == 200
    assert allowed.json()["result"] == {"accepted": True}

    repository = TaskRepository(get_settings().database_path)
    repository.initialize()
    events = repository.list_audit()
    tool_events = [event for event in events if event["event_type"].startswith("tool.")]
    assert {event["event_type"] for event in tool_events} >= {
        "tool.permission_granted",
        "tool.invocation",
    }
    assert "private-input-must-not-enter-audit" not in str(tool_events)
    assert all(event["actor_id"] == "local-owner" for event in tool_events)

    revoked = client.delete("/tools/grants/cloudflare.read")
    assert revoked.status_code == 204
    assert client.get("/tools/grants").json() == []

    denied_again = client.post("/tools/cloudflare.inventory/invoke", json=payload)
    assert denied_again.status_code == 403

    events_after_revoke = repository.list_audit()
    assert any(event["event_type"] == "tool.permission_revoked" for event in events_after_revoke)


def test_failed_tool_execution_is_sanitized_and_audited(monkeypatch):
    client = authenticated_client()

    class ProtectedInput(BaseModel):
        text: str

    class ProtectedOutput(BaseModel):
        accepted: bool

    def fail_handler(_payload):
        raise RuntimeError("private provider failure details")

    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="cloudflare.inventory",
            description="Read Cloudflare inventory metadata without modifying resources.",
            input_model=ProtectedInput,
            output_model=ProtectedOutput,
            handler=fail_handler,
            required_permissions=frozenset({"cloudflare.read"}),
        )
    )
    monkeypatch.setattr(tools_api, "build_tool_registry", lambda: registry)
    assert client.put("/tools/grants/cloudflare.read", json={}).status_code == 200

    response = client.post(
        "/tools/cloudflare.inventory/invoke",
        json={"payload": {"text": "sensitive-input"}},
    )
    assert response.status_code == 502
    assert "private provider failure details" not in response.text

    repository = TaskRepository(get_settings().database_path)
    events = repository.list_audit()
    failure = next(
        event for event in events
        if event["event_type"] == "tool.invocation" and event["outcome"] == "failure"
    )
    assert failure["metadata"]["reason_code"] == "tool_handler_failed"
    assert "sensitive-input" not in str(events)


def test_tool_grants_reject_unsupported_permissions_and_unbounded_expiry():
    client = authenticated_client()
    unsupported = client.put("/tools/grants/cloudflare.write", json={"expires_in_seconds": 3600})
    assert unsupported.status_code == 422
    too_short = client.put("/tools/grants/cloudflare.read", json={"expires_in_seconds": 1})
    assert too_short.status_code == 422
    too_long = client.put("/tools/grants/cloudflare.read", json={"expires_in_seconds": 86401})
    assert too_long.status_code == 422


def test_tool_grant_management_requires_authentication(tmp_path, monkeypatch):
    monkeypatch.setenv("MRH_DATABASE_PATH", str(tmp_path / "test.sqlite3"))
    get_settings.cache_clear()
    client = TestClient(create_app())
    assert client.get("/tools/grants").status_code in (401, 403)
    assert client.put(
        "/tools/grants/cloudflare.read",
        json={"expires_in_seconds": 3600},
    ).status_code in (401, 403)
    assert client.delete("/tools/grants/cloudflare.read").status_code in (401, 403)
    get_settings.cache_clear()
