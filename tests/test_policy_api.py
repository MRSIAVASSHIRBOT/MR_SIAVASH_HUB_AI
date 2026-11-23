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


def test_policy_api_rejects_client_claimed_approval() -> None:
    client = authenticated_client()
    response = client.post(
        "/policy/evaluate",
        json={
            "action": "social.publish",
            "risk_class": "high",
            "external_side_effect": True,
            "user_approved": True,
        },
    )
    assert response.status_code == 422

    evaluated = client.post(
        "/policy/evaluate",
        json={
            "action": "social.publish",
            "risk_class": "high",
            "external_side_effect": True,
        },
    )
    assert evaluated.status_code == 200
    assert evaluated.json()["decision"] == "require_approval"


def test_policy_api_uses_only_the_authenticated_owners_active_grants() -> None:
    from mrhub.infrastructure.database import TaskRepository
    from mrhub.security.audit import AuditLogger
    from mrhub.security.tool_permissions import ToolPermissionService

    client = authenticated_client()
    repository = TaskRepository(get_settings().database_path)
    repository.initialize()
    repository.create_auth_user("other-owner", "other-owner", "22" * 16, "22" * 32)
    service = ToolPermissionService(repository, AuditLogger(repository))
    service.grant("other-owner", "cloudflare.read", 600)

    payload = {
        "action": "cloudflare.inventory",
        "risk_class": "low",
        "required_permissions": ["cloudflare.read"],
    }

    # A caller cannot supply a permission set, even if it contains the required grant.
    forged = client.post(
        "/policy/evaluate",
        json={**payload, "granted_permissions": ["cloudflare.read"]},
    )
    assert forged.status_code == 422

    # Another owner's grant is not visible to this authenticated owner.
    denied = client.post("/policy/evaluate", json=payload)
    assert denied.status_code == 200
    assert denied.json()["decision"] == "deny"

    # The same grant becomes effective only after it is granted to the caller.
    service.grant("local-owner", "cloudflare.read", 600)
    allowed = client.post("/policy/evaluate", json=payload)
    assert allowed.status_code == 200
    assert allowed.json()["decision"] == "allow"

    events = [
        item for item in repository.list_audit()
        if item["event_type"] == "policy.evaluated"
    ]
    assert len(events) == 2
    assert events[-1]["actor_id"] == "local-owner"
    assert events[-1]["metadata"]["granted_permission_count"] == 1
    assert events[-1]["metadata"]["required_permission_count"] == 1
