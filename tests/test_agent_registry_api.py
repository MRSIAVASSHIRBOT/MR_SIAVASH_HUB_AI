from client_helpers import authenticated_client


def test_agent_registry_endpoint_returns_frozen_metadata_without_instructions():
    client = authenticated_client()

    first = client.get("/agent/registry")
    second = client.get("/agent/registry")

    assert first.status_code == second.status_code == 200
    body = first.json()
    assert body["schema_version"] == "agent_registry_manifest.v1"
    assert body["registry_frozen"] is True
    assert body["runtime_registration_enabled"] is False
    assert body["execution_authorized"] is False
    assert body["instructions_exposed"] is False
    assert body["agent_count"] == 6
    assert body == second.json()
    assert all(
        set(item) == {
            "name",
            "version",
            "description",
            "allowed_tools",
            "max_turns",
            "profile_digest",
        }
        for item in body["agents"]
    )
    assert all("instructions" not in item for item in body["agents"])
    assert body["instructions_exposed"] is False
    assert first.headers["cache-control"] == "no-store"


def test_agent_run_fails_closed_when_shared_registry_is_unavailable():
    client = authenticated_client()
    registry = client.app.state.agent_registry
    client.app.state.agent_registry = None
    try:
        response = client.post(
            "/agent/run",
            json={"goal": "Do not run without the reviewed registry."},
        )
    finally:
        client.app.state.agent_registry = registry

    assert response.status_code == 503
    # The app-level exception sanitizer intentionally hides internal 503 details.
    assert response.json()["detail"] == "The service is temporarily unavailable."


def test_agent_registry_endpoint_requires_owner_authentication():
    client = authenticated_client()
    client.headers.pop("Authorization", None)

    response = client.get("/agent/registry")

    assert response.status_code == 401
