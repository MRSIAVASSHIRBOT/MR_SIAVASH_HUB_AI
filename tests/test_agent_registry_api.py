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
    assert "instructions" not in first.text
    assert first.headers["cache-control"] == "no-store"
