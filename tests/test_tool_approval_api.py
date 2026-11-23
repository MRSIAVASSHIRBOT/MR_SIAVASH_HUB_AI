from pydantic import BaseModel, ConfigDict, Field

from client_helpers import authenticated_client
from mrhub.api.routes import tools as tools_api
from mrhub.config import get_settings
from mrhub.domain.tasks import RiskClass
from mrhub.infrastructure.database import TaskRepository
from mrhub.security.audit import AuditLogger
from mrhub.security.tool_approvals import ToolInvocationApprovalStore
from mrhub.security.tool_permissions import ToolPermissionService
from mrhub.tools.registry import ToolDefinition, ToolRegistry


class PublishInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=200)


class PublishOutput(BaseModel):
    accepted: bool


def _registry(handler):
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="content.publish",
            description="Publish one owner-approved content payload.",
            input_model=PublishInput,
            output_model=PublishOutput,
            handler=handler,
            risk_class=RiskClass.HIGH,
            required_permissions=frozenset({"cloudflare.read"}),
            external_side_effect=True,
        )
    )
    return registry


def _client_with_registry(monkeypatch, registry):
    client = authenticated_client()
    monkeypatch.setattr(tools_api, "build_tool_registry", lambda **_kwargs: registry)
    return client


def _grant_read_permission():
    repository = TaskRepository(get_settings().database_path)
    repository.initialize()
    ToolPermissionService(repository, AuditLogger(repository)).grant(
        "local-owner", "cloudflare.read", 600
    )


def test_external_tool_requires_exact_owner_approval_once(monkeypatch):
    calls = []
    registry = _registry(
        lambda payload: calls.append(payload.text) or {"accepted": True}
    )
    client = _client_with_registry(monkeypatch, registry)

    denied_without_grant = client.post(
        "/tools/content.publish/approvals",
        json={"payload": {"text": "approved copy"}},
    )
    assert denied_without_grant.status_code == 403
    assert calls == []

    _grant_read_permission()
    spoofed_approval = client.post(
        "/tools/content.publish/invoke",
        json={
            "payload": {"text": "approved copy"},
            "user_approved": True,
        },
    )
    assert spoofed_approval.status_code == 422
    assert calls == []

    pending = client.post(
        "/tools/content.publish/approvals",
        json={"payload": {"text": "approved copy"}, "expires_in_seconds": 300},
    )
    assert pending.status_code == 201
    approval = pending.json()
    assert approval["status"] == "pending"
    assert approval["owner_review_required"] is True
    assert approval["execution_started"] is False
    assert approval["tools_executed"] is False
    assert len(approval["payload_digest"]) == 64
    assert len(approval["tool_fingerprint"]) == 64
    assert calls == []

    approval_id = approval["approval_id"]
    decision = client.post(
        f"/tools/content.publish/approvals/{approval_id}/decision",
        json={"decision": "approved"},
    )
    assert decision.status_code == 200
    assert decision.json()["status"] == "approved"
    assert calls == []

    mismatched = client.post(
        "/tools/content.publish/invoke",
        json={
            "payload": {"text": "different payload"},
            "approval_id": approval_id,
        },
    )
    assert mismatched.status_code == 409
    assert calls == []

    invoked = client.post(
        "/tools/content.publish/invoke",
        json={
            "payload": {"text": "approved copy"},
            "approval_id": approval_id,
        },
    )
    assert invoked.status_code == 200
    assert invoked.json()["executed"] is True
    assert invoked.json()["approval_consumed"] is True
    assert calls == ["approved copy"]

    replay = client.post(
        "/tools/content.publish/invoke",
        json={
            "payload": {"text": "approved copy"},
            "approval_id": approval_id,
        },
    )
    assert replay.status_code == 409
    assert calls == ["approved copy"]

    repository = TaskRepository(get_settings().database_path)
    events = repository.list_audit()
    approval_events = [
        item for item in events
        if item["event_type"] in {"tool.approval_requested", "tool.approval_decided"}
    ]
    assert [item["event_type"] for item in approval_events] == [
        "tool.approval_requested",
        "tool.approval_decided",
    ]
    assert all(item["actor_id"] == "local-owner" for item in approval_events)
    assert "approved copy" not in str(approval_events)
    with repository._connection() as connection:
        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(tool_invocation_approvals)")
        }
        stored = connection.execute(
            "SELECT * FROM tool_invocation_approvals WHERE approval_id = ?",
            (approval_id,),
        ).fetchone()
    assert "payload" not in columns
    assert "payload_json" not in columns
    assert "approved copy" not in str(dict(stored))


def test_rejected_approval_never_invokes_handler(monkeypatch):
    calls = []
    registry = _registry(
        lambda payload: calls.append(payload.text) or {"accepted": True}
    )
    client = _client_with_registry(monkeypatch, registry)
    _grant_read_permission()

    pending = client.post(
        "/tools/content.publish/approvals",
        json={"payload": {"text": "reject this"}},
    )
    assert pending.status_code == 201
    approval_id = pending.json()["approval_id"]

    rejected = client.post(
        f"/tools/content.publish/approvals/{approval_id}/decision",
        json={"decision": "rejected"},
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"

    response = client.post(
        "/tools/content.publish/invoke",
        json={
            "payload": {"text": "reject this"},
            "approval_id": approval_id,
        },
    )
    assert response.status_code == 409
    assert calls == []


def test_changed_handler_definition_expires_pending_approval(monkeypatch):
    first_calls = []
    second_calls = []
    first = _registry(
        lambda payload: first_calls.append(payload.text) or {"accepted": True}
    )
    second = _registry(
        lambda payload: second_calls.append(payload.text) or {"accepted": True}
    )
    client = _client_with_registry(monkeypatch, first)
    _grant_read_permission()

    pending = client.post(
        "/tools/content.publish/approvals",
        json={"payload": {"text": "revalidate after deploy"}},
    )
    assert pending.status_code == 201
    approval_id = pending.json()["approval_id"]

    monkeypatch.setattr(tools_api, "build_tool_registry", lambda **_kwargs: second)
    stale = client.post(
        f"/tools/content.publish/approvals/{approval_id}/decision",
        json={"decision": "approved"},
    )
    assert stale.status_code == 409
    assert first_calls == []
    assert second_calls == []


def test_tool_approval_store_is_owner_scoped_and_single_use():
    authenticated_client()
    repository = TaskRepository(get_settings().database_path)
    repository.initialize()
    store = ToolInvocationApprovalStore(repository)
    record = store.create(
        approval_id="12345678-1234-5678-1234-567812345678",
        owner_user_id="local-owner",
        tool_name="content.publish",
        payload_digest="a" * 64,
        tool_fingerprint="b" * 64,
    )
    assert record["status"] == "pending"

    wrong_owner = store.consume(
        record["approval_id"],
        owner_user_id="another-owner",
        tool_name="content.publish",
        payload_digest="a" * 64,
        tool_fingerprint="b" * 64,
    )
    assert wrong_owner is False

    decided = store.decide(
        record["approval_id"],
        owner_user_id="local-owner",
        tool_name="content.publish",
        tool_fingerprint="b" * 64,
        decision="approved",
    )
    assert decided is not None
    assert decided["status"] == "approved"

    consumed = store.consume(
        record["approval_id"],
        owner_user_id="local-owner",
        tool_name="content.publish",
        payload_digest="a" * 64,
        tool_fingerprint="b" * 64,
    )
    replayed = store.consume(
        record["approval_id"],
        owner_user_id="local-owner",
        tool_name="content.publish",
        payload_digest="a" * 64,
        tool_fingerprint="b" * 64,
    )
    assert consumed is True
    assert replayed is False

    with repository._connection() as connection:
        stored = connection.execute(
            "SELECT status, payload_digest, tool_fingerprint FROM tool_invocation_approvals "
            "WHERE approval_id = ?",
            (record["approval_id"],),
        ).fetchone()
    assert tuple(stored) == ("consumed", "a" * 64, "b" * 64)
    assert "revalidate after deploy" not in str(stored)
