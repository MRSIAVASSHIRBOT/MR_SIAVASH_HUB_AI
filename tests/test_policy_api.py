from client_helpers import authenticated_client
from mrhub.config import get_settings


def test_high_risk_task_waits_for_approval(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("MRH_DATABASE_PATH", str(tmp_path / "approval.sqlite3"))
    get_settings.cache_clear()
    client = authenticated_client()
    response = client.post(
        "/tasks",
        json={"task_type": "content.publish"},
    )
    assert response.status_code == 201
    assert response.json()["status"] == "waiting_approval"
    get_settings.cache_clear()


def test_unknown_task_type_requires_approval(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("MRH_DATABASE_PATH", str(tmp_path / "unknown.sqlite3"))
    get_settings.cache_clear()
    client = authenticated_client()
    response = client.post(
        "/tasks",
        json={"task_type": "unregistered.action", "risk_class": "low"},
    )
    assert response.status_code == 201
    assert response.json()["status"] == "waiting_approval"
    assert response.json()["risk_class"] == "high"
    get_settings.cache_clear()


def test_job_cancel_endpoint(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("MRH_DATABASE_PATH", str(tmp_path / "cancel.sqlite3"))
    get_settings.cache_clear()
    client = authenticated_client()
    created = client.post("/tasks", json={"task_type": "demo.echo"})
    task_id = created.json()["task_id"]
    cancelled = client.post(f"/jobs/{task_id}/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    get_settings.cache_clear()




def test_policy_api_rejects_client_supplied_policy_facts() -> None:
    client = authenticated_client()
    response = client.post(
        "/policy/evaluate",
        json={
            "action": "cloudflare.inventory.snapshot",
            "risk_class": "low",
            "granted_permissions": ["cloudflare.read"],
            "required_permissions": [],
            "external_side_effect": False,
            "user_approved": True,
        },
    )

    assert response.status_code == 422


def test_policy_api_unknown_action_requires_approval() -> None:
    client = authenticated_client()
    response = client.post(
        "/policy/evaluate",
        json={"action": "social.publish"},
    )

    assert response.status_code == 200
    assert response.json()["decision"] == "require_approval"
    assert response.json()["reason"] == "Unregistered action requires explicit review"


def test_policy_api_uses_registered_metadata_and_only_owner_active_grants(
    monkeypatch,
) -> None:
    from pydantic import BaseModel, ConfigDict

    from mrhub.api.routes import policy as policy_routes
    from mrhub.domain.tasks import RiskClass
    from mrhub.infrastructure.database import TaskRepository
    from mrhub.security.audit import AuditLogger
    from mrhub.security.tool_permissions import ToolPermissionService
    from mrhub.tools.registry import ToolDefinition, ToolRegistry

    class EmptyInput(BaseModel):
        model_config = ConfigDict(extra="forbid")

    class EmptyOutput(BaseModel):
        ok: bool = True

    def handler(_payload: BaseModel) -> BaseModel:
        return EmptyOutput()

    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="cloudflare.inventory.snapshot",
            description="Read bounded Cloudflare inventory metadata.",
            input_model=EmptyInput,
            output_model=EmptyOutput,
            handler=handler,
            risk_class=RiskClass.LOW,
            required_permissions=frozenset({"cloudflare.read"}),
            external_side_effect=False,
        )
    )
    registry.register(
        ToolDefinition(
            name="content.publish",
            description="Publish content to an external destination.",
            input_model=EmptyInput,
            output_model=EmptyOutput,
            handler=handler,
            risk_class=RiskClass.HIGH,
            external_side_effect=True,
        )
    )
    monkeypatch.setattr(
        policy_routes,
        "build_tool_registry",
        lambda *, owner_user_id: registry,
    )

    client = authenticated_client()
    repository = TaskRepository(get_settings().database_path)
    repository.initialize()
    repository.create_auth_user("other-owner", "other-owner", "22" * 16, "22" * 32)
    service = ToolPermissionService(repository, AuditLogger(repository))
    service.grant("other-owner", "cloudflare.read", 600)

    payload = {"action": "cloudflare.inventory.snapshot"}

    # A grant owned by another account cannot satisfy this user's action.
    denied = client.post("/policy/evaluate", json=payload)
    assert denied.status_code == 200
    assert denied.json()["decision"] == "deny"

    # Only an active grant for the authenticated owner satisfies the registry requirement.
    service.grant("local-owner", "cloudflare.read", 600)
    allowed = client.post("/policy/evaluate", json=payload)
    assert allowed.status_code == 200
    assert allowed.json()["decision"] == "allow"
    assert allowed.json()["evaluation_only"] is True
    assert allowed.json()["execution_authorized"] is False
    assert allowed.json()["action_executed"] is False

    events = [
        item for item in repository.list_audit()
        if item["event_type"] == "policy.evaluated"
    ]
    assert len(events) == 2
    assert events[-1]["actor_id"] == "local-owner"
    assert events[-1]["metadata"]["risk_class"] == "low"
    assert events[-1]["metadata"]["granted_permission_count"] == 1
    assert events[-1]["metadata"]["required_permission_count"] == 1

    # High-risk and external-effect classification comes from server metadata.
    review_required = client.post(
        "/policy/evaluate",
        json={"action": "content.publish"},
    )
    assert review_required.status_code == 200
    assert review_required.json()["decision"] == "require_approval"

def test_device_app_launch_tool_is_marked_as_external_side_effect() -> None:
    from mrhub.tools.builtins import build_tool_registry

    registry = build_tool_registry(owner_user_id="policy-test-owner")
    tool = registry.get("device.app_launch.submit")

    assert tool.external_side_effect is True
