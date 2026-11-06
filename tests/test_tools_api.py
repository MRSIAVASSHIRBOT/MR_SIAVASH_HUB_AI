from fastapi.testclient import TestClient
from pydantic import BaseModel

from client_helpers import authenticated_client
from mrhub.config import get_settings
from mrhub.main import create_app
from mrhub.api.routes import tools as tools_api
from mrhub.domain.tasks import RiskClass
from mrhub.infrastructure.database import TaskRepository
from mrhub.tools.registry import ToolDefinition, ToolRegistry


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


def test_tool_invoke_rejects_unregistered_tool():
    client = authenticated_client()
    response = client.post(
        "/tools/shell.execute/invoke",
        json={"payload": {"command": "echo not executed"}},
    )
    assert response.status_code == 404


def test_tool_invoke_validates_payload_without_echoing_input():
    client = authenticated_client()
    response = client.post("/tools/text.echo/invoke", json={"payload": {"text": ""}})
    assert response.status_code == 422
    assert response.json()["detail"] == "Tool input validation failed"
    assert "text" not in response.text


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
