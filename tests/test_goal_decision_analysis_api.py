from client_helpers import authenticated_client


def test_goal_analysis_endpoint_is_deterministic_and_does_not_start_execution(monkeypatch):
    import mrhub.api.routes.agent as agent_routes

    def provider_must_not_be_selected(*_args, **_kwargs):
        raise AssertionError("Goal preflight analysis must not select or invoke a provider")

    monkeypatch.setattr(agent_routes, "build_model_router", provider_must_not_be_selected)

    client = authenticated_client()
    response = client.post(
        "/agent/work-orders/analyze",
        json={"goal": "Compare the latest Python release with official documentation."},
    )

    assert response.status_code == 200
    body = response.json()
    analysis = body["analysis"]
    assert analysis["research_required"] is True
    assert analysis["tool_use_required"] is False
    assert analysis["analysis_source"] == "deterministic_heuristic"
    assert analysis["authorization_checked"] is False
    assert analysis["execution_started"] is False
    assert body["planning_only"] is True
    assert body["tools_executed"] is False
    assert body["permissions_changed"] is False


def test_goal_analysis_endpoint_requires_authentication():
    from fastapi.testclient import TestClient

    from mrhub.main import create_app

    client = TestClient(create_app())
    response = client.post(
        "/agent/work-orders/analyze",
        json={"goal": "Explain what a database is."},
    )
    assert response.status_code == 401
