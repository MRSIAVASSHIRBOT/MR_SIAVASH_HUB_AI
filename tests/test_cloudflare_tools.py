from client_helpers import authenticated_client
from mrhub.config import get_settings
from mrhub.infrastructure.database import TaskRepository
from mrhub.integrations.cloudflare import (
    D1DatabaseSummary,
    WorkerRoute,
    WorkerSettingsSummary,
    WorkerSummary,
)
from mrhub.tools import builtins


class FakeCloudflareGateway:
    def __init__(self):
        self.calls = []

    def list_workers(self):
        self.calls.append("workers")
        return [WorkerSummary(id="hub-gateway", etag="etag-1")]

    def list_worker_routes(self):
        self.calls.append("routes")
        return [
            WorkerRoute(
                id="route-1",
                pattern="example.com/api/*",
                script="hub-gateway",
                zone_id="a" * 32,
            )
        ]

    def list_d1_databases(self):
        self.calls.append("databases")
        return [D1DatabaseSummary(uuid="db-1", name="hub-metadata")]

    def get_worker_settings(self, script_name):
        self.calls.append(f"settings:{script_name}")
        return WorkerSettingsSummary(
            compatibility_date="2026-11-06",
            usage_model="standard",
            bindings=[],
        )


def test_cloudflare_tools_are_not_registered_when_gateway_is_disabled(monkeypatch):
    for key in (
        "MRH_CLOUDFLARE_GATEWAY_ENABLED",
        "MRH_CLOUDFLARE_GATEWAY_BASE_URL",
        "MRH_CLOUDFLARE_GATEWAY_TOKEN",
    ):
        monkeypatch.delenv(key, raising=False)
    get_settings.cache_clear()
    try:
        catalog = builtins.build_tool_registry().catalog()
        assert [item["name"] for item in catalog] == ["text.echo"]
    finally:
        get_settings.cache_clear()


def test_cloudflare_tools_register_only_with_gateway_and_require_owner_grant(monkeypatch):
    gateway = FakeCloudflareGateway()
    monkeypatch.setattr(
        builtins,
        "build_cloudflare_gateway_client",
        lambda _settings: gateway,
    )

    registry = builtins.build_tool_registry()
    names = {item["name"] for item in registry.catalog()}
    assert names == {
        "text.echo",
        "cloudflare.workers.list",
        "cloudflare.worker_routes.list",
        "cloudflare.d1_databases.list",
        "cloudflare.worker.settings.read",
    }
    cloudflare_items = [
        item for item in registry.catalog() if item["name"].startswith("cloudflare.")
    ]
    assert all(item["required_permissions"] == ["cloudflare.read"] for item in cloudflare_items)
    assert all(item["external_side_effect"] is False for item in cloudflare_items)

    denied = False
    try:
        registry.invoke("cloudflare.workers.list", {})
    except PermissionError:
        denied = True
    assert denied is True
    assert gateway.calls == []


def test_cloudflare_api_invocation_is_owner_grant_gated_and_audited(monkeypatch):
    gateway = FakeCloudflareGateway()
    monkeypatch.setattr(
        builtins,
        "build_cloudflare_gateway_client",
        lambda _settings: gateway,
    )
    client = authenticated_client()

    denied = client.post("/tools/cloudflare.workers.list/invoke", json={"payload": {}})
    assert denied.status_code == 403
    assert gateway.calls == []

    granted = client.put(
        "/tools/grants/cloudflare.read",
        json={"expires_in_seconds": 3600},
    )
    assert granted.status_code == 200

    listed = client.post("/tools/cloudflare.workers.list/invoke", json={"payload": {}})
    assert listed.status_code == 200
    assert listed.headers["cache-control"] == "no-store"
    assert listed.json()["result"]["workers"] == [
        {"id": "hub-gateway", "etag": "etag-1", "created_on": None, "modified_on": None}
    ]
    assert gateway.calls == ["workers"]

    invalid = client.post(
        "/tools/cloudflare.worker.settings.read/invoke",
        json={"payload": {"script_name": "../invalid"}},
    )
    assert invalid.status_code == 422
    assert gateway.calls == ["workers"]

    settings = client.post(
        "/tools/cloudflare.worker.settings.read/invoke",
        json={"payload": {"script_name": "hub-gateway"}},
    )
    assert settings.status_code == 200
    assert gateway.calls == ["workers", "settings:hub-gateway"]

    repository = TaskRepository(get_settings().database_path)
    events = repository.list_audit()
    invocations = [event for event in events if event["event_type"] == "tool.invocation"]
    assert len(invocations) >= 3
    assert all(event["actor_id"] == "local-owner" for event in invocations)

    revoked = client.delete("/tools/grants/cloudflare.read")
    assert revoked.status_code == 204
    denied_again = client.post("/tools/cloudflare.workers.list/invoke", json={"payload": {}})
    assert denied_again.status_code == 403
    assert gateway.calls == ["workers", "settings:hub-gateway"]


def test_cloudflare_tool_outputs_exclude_gateway_credentials(monkeypatch):
    gateway = FakeCloudflareGateway()
    monkeypatch.setattr(
        builtins,
        "build_cloudflare_gateway_client",
        lambda _settings: gateway,
    )
    client = authenticated_client()
    assert client.put("/tools/grants/cloudflare.read", json={}).status_code == 200

    response = client.post(
        "/tools/cloudflare.worker_routes.list/invoke",
        json={"payload": {}},
    )
    assert response.status_code == 200
    body = response.text.lower()
    assert "gateway-test-token" not in body
    assert "authorization" not in body
    assert response.json()["result"]["routes"][0]["script"] == "hub-gateway"
