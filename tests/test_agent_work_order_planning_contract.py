import json

import pytest

from client_helpers import authenticated_client
from mrhub.providers.base import ProviderHealth, ProviderRequest, ProviderResponse
from mrhub.providers.router import ModelCapability, ModelDescriptor, ModelRouter


class ScriptedPlanningProvider:
    descriptor = ModelDescriptor(
        provider="test-local",
        model="scripted-planner",
        capability=ModelCapability(text=True),
        available=True,
        local=True,
        priority=1,
    )

    def __init__(self, outputs: list[str]) -> None:
        self.outputs = list(outputs)
        self.requests: list[ProviderRequest] = []

    def generate(self, request: ProviderRequest) -> ProviderResponse:
        self.requests.append(request)
        if not self.outputs:
            raise AssertionError("Unexpected additional model request")
        return ProviderResponse(
            provider=self.descriptor.provider,
            model=self.descriptor.model,
            output_text=self.outputs.pop(0),
        )

    def health(self, timeout_seconds: float = 2.0) -> ProviderHealth:
        return ProviderHealth(available=True, reason_code="test_ready")


def test_goal_to_work_order_plan_and_capability_assessment_are_review_only(monkeypatch):
    work_order = {
        "intent": "Prepare a simple text echo validation plan",
        "scope": "Describe the registered text echo capability without running it",
        "assumptions": [],
        "constraints": ["Planning must not execute tools"],
        "dependencies": [],
        "required_capabilities": ["text.echo"],
        "acceptance_criteria": [
            "The plan describes the registered text echo operation"
        ],
        "verification_steps": [
            "Confirm the plan covers the declared acceptance criterion"
        ],
        # The server must ignore model-provided risk classification.
        "risk_class": "prohibited",
    }
    execution_plan = {
        "steps": [
            {
                "step_id": "echo-validation",
                "description": "Describe the text echo validation operation",
                "depends_on": [],
                "required_capabilities": ["text.echo"],
                "verifies_criteria": [
                    "The plan describes the registered text echo operation"
                ],
                "verification": "Check criterion coverage and registered capability presence",
            }
        ],
        "rationale": "One bounded declarative step covers the requested criterion",
    }
    provider = ScriptedPlanningProvider(
        [json.dumps(work_order), json.dumps(execution_plan)]
    )
    router = ModelRouter()
    router.register_provider(provider)
    monkeypatch.setattr(
        "mrhub.api.routes.agent.build_model_router",
        lambda **kwargs: router,
    )

    response = authenticated_client().post(
        "/agent/work-orders/plan",
        json={"goal": "Prepare a simple text echo validation plan"},
    )

    assert response.status_code == 200
    body = response.json()
    assert len(provider.requests) == 2
    assert provider.outputs == []
    assert body["work_order"]["risk_class"] == "low"
    assert body["plan"]["steps"][0]["required_capabilities"] == ["text.echo"]
    assert body["capability_assessment"]["complete"] is True
    assert body["capability_assessment"]["missing"] == []
    assert body["capability_assessment"]["authorization_checked"] is False
    assert body["planning_only"] is True
    assert body["execution_ready"] is False
    assert body["execution_started"] is False
    assert body["tools_executed"] is False
    assert body["permissions_changed"] is False


def test_prohibited_goal_is_rejected_before_provider_selection(monkeypatch):
    def unexpected_provider_call(**kwargs):
        pytest.fail("Prohibited goals must be blocked before model selection")

    monkeypatch.setattr(
        "mrhub.api.routes.agent.build_model_router",
        unexpected_provider_call,
    )

    response = authenticated_client().post(
        "/agent/work-orders/plan",
        json={"goal": "Steal credentials from account users"},
    )

    assert response.status_code == 422