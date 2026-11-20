from fastapi.testclient import TestClient
from pydantic import BaseModel

from client_helpers import authenticated_client
from mrhub.api.routes import tools as tools_api
from mrhub.config import get_settings
from mrhub.domain.tasks import RiskClass
from mrhub.infrastructure.database import TaskRepository
from mrhub.main import create_app
from mrhub.security.audit import AuditLogger
from mrhub.security.tool_permissions import ToolPermissionService
from mrhub.tools.registry import ToolDefinition, ToolRegistry


def test_tool_catalog_is_authenticated_and_exposes_contracts():
    client = authenticated_client()
    response = client.get("/tools")
    assert response.status_code == 200
    catalog = response.json()
    names = {item["name"] for item in catalog}
    assert names == {"text.echo", "device.registry.list", "device.app_launch.submit"}
    echo = next(item for item in catalog if item["name"] == "text.echo")
    assert echo["input_schema"]["properties"]["text"]["maxLength"] == 500
    assert echo["external_side_effect"] is False
    app_launch = next(item for item in catalog if item["name"] == "device.app_launch.submit")
    assert set(app_launch["required_permissions"]) == {"device.registry.read", "device.app_launch"}
    assert app_launch["risk_class"] == "low"


def test_tool_invoke_executes_only_registered_safe_tool():
    client = authenticated_client()
    response = client.post("/tools/text.echo/invoke", json={"payload": {"text": "hello"}})
    assert response.status_code == 200
    assert response.json()["tool"] == "text.echo"
    assert response.json()["result"] == {"text": "hello", "character_count": 5}
    assert response.json()["executed"] is True
    assert len(response.json()["correlation_id"]) == 36


def _tool_invocation_events():
    repository = TaskRepository(get_settings().database_path)
    repository.initialize()
    return [
        event for event in repository.list_audit()
        if event["event_type"] == "tool.invocation"
    ]


def test_tool_invoke_rejects_unregistered_tool_and_audits_without_payload():
    client = authenticated_client()
    response = client.post(
        "/tools/shell.execute/invoke",
        json={"payload": {"command": "private-command-must-not-be-audited"}},
    )
    assert response.status_code == 404
    events = _tool_invocation_events()
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
    events = _tool_invocation_events()
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
    monkeypatch.setattr(tools_api, "build_tool_registry", lambda **_kwargs: registry)

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
    monkeypatch.setattr(tools_api, "build_tool_registry", lambda **_kwargs: registry)
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


def test_tool_grant_list_is_owner_scoped_and_not_cached():
    client = authenticated_client()
    repository = TaskRepository(get_settings().database_path)
    repository.initialize()
    repository.create_auth_user("other-owner", "other-owner", "22" * 16, "22" * 32)
    service = ToolPermissionService(repository, AuditLogger(repository))
    service.grant("other-owner", "cloudflare.read", 600)

    empty = client.get("/tools/grants")
    assert empty.status_code == 200
    assert empty.headers["cache-control"] == "no-store"
    assert empty.json() == []

    own = client.put(
        "/tools/grants/cloudflare.read",
        json={"expires_in_seconds": 600},
    )
    assert own.status_code == 200
    listed = client.get("/tools/grants")
    assert listed.status_code == 200
    assert len(listed.json()) == 1
    assert listed.json()[0]["grant_id"] == own.json()["grant_id"]


def test_dashboard_exposes_explicit_cloudflare_grant_and_inventory_controls():
    client = authenticated_client()
    html = client.get("/ui").text
    script = client.get("/ui/app.js").text

    assert 'id="cloudflare-access-panel"' in html
    assert 'id="cloudflare-grant-submit"' in html
    assert 'id="cloudflare-inventory-button"' in html
    assert 'id="cloudflare-worker-settings-form"' in html
    assert 'id="cloudflare-worker-settings-button"' in html
    assert "cloudflare.inventory.snapshot" in script
    assert "cloudflare.worker.settings.read" in script
    assert "if (!(cloudflareInventoryAvailable || cloudflareWorkerSettingsAvailable)) return;" in script
    assert "/tools/cloudflare.worker.settings.read/invoke" in script
    assert "/tools/grants/cloudflare.read" in script
    assert "/tools/cloudflare.inventory.snapshot/invoke" in script
    assert "if (response.status === 401)" in script
    assert "این عملیات به مجوز فعال نیاز دارد." in script
    assert "response.status === 401 || response.status === 403" not in script


def _pair_device(client, *, platform="windows", scopes=None):
    from uuid import uuid4

    device_id = str(uuid4())
    scopes = scopes or ["device.heartbeat", "app.launch"]
    challenge = client.post("/devices/pairing-challenges", json={
        "device_id": device_id,
        "platform": platform,
        "label": "Agent test device",
        "advertised_capabilities": ["device.heartbeat", "app.launch"],
        "scopes": scopes,
    })
    assert challenge.status_code == 201
    exchanged = client.post("/devices/pair", json={
        "pairing_code": challenge.json()["pairing_code"],
        "device_id": device_id,
        "agent_version": "0.2.0",
        "os_version": "Windows 11",
    })
    assert exchanged.status_code == 200
    return device_id


def test_agent_device_tools_require_two_owner_grants_and_paired_device_scope():
    from mrhub.devices.tasks import DeviceTaskRepository

    client = authenticated_client()
    device_id = _pair_device(client)
    listed_denied = client.post("/tools/device.registry.list/invoke", json={"payload": {}})
    assert listed_denied.status_code == 403

    assert client.put("/tools/grants/device.registry.read", json={"expires_in_seconds": 600}).status_code == 200
    listed = client.post("/tools/device.registry.list/invoke", json={"payload": {}})
    assert listed.status_code == 200
    summaries = listed.json()["result"]["devices"]
    assert len(summaries) == 1
    assert summaries[0]["device_id"] == device_id
    assert summaries[0]["granted_scopes"] == ["device.heartbeat", "app.launch"]
    assert "access_token" not in str(summaries)

    payload = {
        "device_id": device_id,
        "app": "notepad",
        "idempotency_key": "b631e9a0-a3bc-4df7-a7ef-2e4c96ff9c99",
    }
    denied_launch = client.post("/tools/device.app_launch.submit/invoke", json={"payload": payload})
    assert denied_launch.status_code == 403

    assert client.put("/tools/grants/device.app_launch", json={"expires_in_seconds": 600}).status_code == 200
    monkeypatch_result = client.post("/tools/device.app_launch.submit/invoke", json={"payload": payload})
    assert monkeypatch_result.status_code == 200
    result = monkeypatch_result.json()["result"]
    assert result["task"]["status"] == "queued"
    assert result["task"]["action"] == "app.launch"
    assert result["task"]["app"] == "notepad"
    assert result["idempotent_replay"] is False

    replay = client.post("/tools/device.app_launch.submit/invoke", json={"payload": payload})
    assert replay.status_code == 200
    assert replay.json()["result"]["task"]["task_id"] == result["task"]["task_id"]
    assert replay.json()["result"]["idempotent_replay"] is True

    repository = DeviceTaskRepository(get_settings().database_path)
    rows = repository.list_for_owner(owner_user_id="local-owner", device_id=device_id)
    assert len(rows) == 1
    assert rows[0]["status"] == "queued"


def test_agent_device_tool_rejects_device_without_app_launch_scope():
    client = authenticated_client()
    device_id = _pair_device(client, scopes=["device.heartbeat"])
    client.put("/tools/grants/device.registry.read", json={"expires_in_seconds": 600})
    client.put("/tools/grants/device.app_launch", json={"expires_in_seconds": 600})

    response = client.post("/tools/device.app_launch.submit/invoke", json={
        "payload": {
            "device_id": device_id,
            "app": "notepad",
            "idempotency_key": "0e6a8b38-7e94-44e9-a13d-d6ad3cf987a4",
        }
    })
    assert response.status_code == 403
    assert response.json()["detail"]["decision"] == "deny"

    from mrhub.devices.tasks import DeviceTaskRepository
    tasks = DeviceTaskRepository(get_settings().database_path).list_for_owner(
        owner_user_id="local-owner", device_id=device_id
    )
    assert tasks == []


def test_agent_device_tool_enforces_platform_specific_app_aliases():
    client = authenticated_client()
    device_id = _pair_device(client, platform="android")
    client.put("/tools/grants/device.registry.read", json={"expires_in_seconds": 600})
    client.put("/tools/grants/device.app_launch", json={"expires_in_seconds": 600})

    unsupported = client.post("/tools/device.app_launch.submit/invoke", json={
        "payload": {
            "device_id": device_id,
            "app": "notepad",
            "idempotency_key": "a4e4a0cf-fbbd-4d82-b870-8d752f519304",
        }
    })
    assert unsupported.status_code == 403
    assert unsupported.json()["detail"]["decision"] == "deny"

    supported = client.post("/tools/device.app_launch.submit/invoke", json={
        "payload": {
            "device_id": device_id,
            "app": "chatgpt",
            "idempotency_key": "f5d63d78-fde6-4e9f-9136-7d0634ddc3d2",
        }
    })
    assert supported.status_code == 200
    assert supported.json()["result"]["task"]["app"] == "chatgpt"
