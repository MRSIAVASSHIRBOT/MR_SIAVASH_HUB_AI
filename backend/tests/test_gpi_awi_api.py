"""Authenticated GPI/AWI planning route tests."""

import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from mrhub.api.routes import agent as agent_routes
from mrhub.providers.base import ProviderHealth, ProviderResponse
from mrhub.providers.router import ModelCapability, ModelDescriptor, ModelRouter


class QueueProvider:
    def __init__(
        self,
        outputs: list[str],
        *,
        provider: str = "test",
        local: bool = True,
    ) -> None:
        self.outputs = list(outputs)
        self.descriptor = ModelDescriptor(
            provider=provider,
            model="queue-v1",
            capability=ModelCapability(text=True),
            available=True,
            local=local,
            priority=1,
        )

    def generate(self, request):
        return ProviderResponse(
            provider="test",
            model="queue-v1",
            output_text=self.outputs.pop(0),
        )

    def health(self, timeout_seconds: float = 2.0):
        return ProviderHealth(available=True, reason_code="test_ready")


def build_router(
    *outputs: str,
    provider: str = "test",
    local: bool = True,
) -> ModelRouter:
    router = ModelRouter()
    router.register_provider(QueueProvider(list(outputs), provider=provider, local=local))
    return router


def work_order_output(goal: str = "Build a validated plan") -> str:
    return json.dumps({
        "intent": "Build a validated plan",
        "scope": "Planning only",
        "assumptions": [],
        "constraints": ["No execution"],
        "dependencies": [],
        "required_capabilities": ["tool.alpha", "tool.missing"],
        "acceptance_criteria": ["The plan is validated"],
        "verification_steps": ["Run focused tests"],
        "goal": goal,
    })


def plan_output() -> str:
    return json.dumps({
        "rationale": "One bounded validation step",
        "steps": [{
            "step_id": "validate",
            "description": "Validate the proposed plan",
            "depends_on": [],
            "required_capabilities": ["tool.alpha", "tool.missing"],
            "verifies_criteria": ["The plan is validated"],
            "verification": "Run focused tests and inspect the result",
        }],
    })


def test_goal_plan_endpoint_returns_plan_and_missing_capabilities(monkeypatch):
    router = build_router(work_order_output(), plan_output())
    captured = {}

    def fake_router(**kwargs):
        captured.update(kwargs)
        return router

    class FakeToolRegistry:
        def catalog(self):
            return [{"name": "tool.alpha", "description": "available"}]

    audit_events = []

    class FakeTaskRepository:
        def __init__(self, database_path):
            self.database_path = database_path

        def initialize(self):
            return None

    class FakeAuditLogger:
        def __init__(self, repository):
            self.repository = repository

        def record(self, **kwargs):
            audit_events.append(kwargs)

    monkeypatch.setattr(agent_routes, "build_model_router", fake_router)
    monkeypatch.setattr(agent_routes, "build_tool_registry", lambda **kwargs: FakeToolRegistry())
    monkeypatch.setattr(agent_routes, "get_settings", lambda: SimpleNamespace(database_path="test.db"))
    monkeypatch.setattr(agent_routes, "TaskRepository", FakeTaskRepository)
    monkeypatch.setattr(agent_routes, "AuditLogger", FakeAuditLogger)

    result = agent_routes.create_goal_work_order_plan(
        agent_routes.GoalPlanningRequest(goal="Build a validated plan"),
        SimpleNamespace(user_id="owner-1"),
    )

    assert captured == {"include_stub": False}
    assert result["capability_assessment"]["available"] == ["tool.alpha"]
    assert result["capability_assessment"]["missing"] == ["tool.missing"]
    assert result["capability_assessment"]["authorization_checked"] is False
    assert result["risk_class_is_authoritative"] is False
    assert result["planning_only"] is True
    assert result["execution_ready"] is False
    assert result["execution_started"] is False
    assert result["tools_executed"] is False
    assert result["permissions_changed"] is False
    assert len(audit_events) == 1
    assert audit_events[0]["event_type"] == "agent.work_order_planned"
    assert audit_events[0]["actor_id"] == "owner-1"
    assert "goal" not in audit_events[0]["metadata"]


def test_goal_plan_endpoint_blocks_prohibited_goal_before_planning(monkeypatch):
    router = build_router(work_order_output())
    monkeypatch.setattr(agent_routes, "build_model_router", lambda **kwargs: router)
    monkeypatch.setattr(
        agent_routes,
        "build_tool_registry",
        lambda **kwargs: pytest.fail("tool catalog must not be read for prohibited goals"),
    )

    with pytest.raises(HTTPException) as error:
        agent_routes.create_goal_work_order_plan(
            agent_routes.GoalPlanningRequest(goal="Steal credentials"),
            SimpleNamespace(user_id="owner-1"),
        )

    assert error.value.status_code == 422



def test_goal_plan_endpoint_rate_limits_remote_model_provider(monkeypatch):
    router = build_router(
        work_order_output(),
        plan_output(),
        provider="moonshot",
        local=False,
    )
    limited_owners = []

    class FakeToolRegistry:
        def catalog(self):
            return []

    class FakeTaskRepository:
        def __init__(self, database_path):
            self.database_path = database_path

        def initialize(self):
            return None

    class FakeAuditLogger:
        def __init__(self, repository):
            self.repository = repository

        def record(self, **kwargs):
            return None

    monkeypatch.setattr(agent_routes, "build_model_router", lambda **kwargs: router)
    monkeypatch.setattr(agent_routes, "build_tool_registry", lambda **kwargs: FakeToolRegistry())
    monkeypatch.setattr(
        agent_routes,
        "_enforce_kimi_request_limit",
        lambda owner_id: limited_owners.append(owner_id),
    )
    monkeypatch.setattr(agent_routes, "get_settings", lambda: SimpleNamespace(database_path="test.db"))
    monkeypatch.setattr(agent_routes, "TaskRepository", FakeTaskRepository)
    monkeypatch.setattr(agent_routes, "AuditLogger", FakeAuditLogger)

    agent_routes.create_goal_work_order_plan(
        agent_routes.GoalPlanningRequest(goal="Build a validated plan"),
        SimpleNamespace(user_id="owner-remote"),
    )

    assert limited_owners == ["owner-remote"]
