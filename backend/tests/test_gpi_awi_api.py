"""Authenticated GPI/AWI planning route tests."""

import json
import sqlite3
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
        self.calls = 0
        self.descriptor = ModelDescriptor(
            provider=provider,
            model="queue-v1",
            capability=ModelCapability(text=True),
            available=True,
            local=local,
            priority=1,
        )

    def generate(self, request):
        self.calls += 1
        return ProviderResponse(
            provider=self.descriptor.provider,
            model=self.descriptor.model,
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


def work_order_output(
    goal: str = "Build a validated plan",
    **overrides: object,
) -> str:
    payload: dict[str, object] = {
        "intent": "Build a validated plan",
        "scope": "Planning only",
        "assumptions": [],
        "constraints": ["No execution"],
        "dependencies": [],
        "required_capabilities": ["tool.alpha", "tool.missing"],
        "acceptance_criteria": ["The plan is validated"],
        "verification_steps": ["Run focused tests"],
        "goal": goal,
    }
    payload.update(overrides)
    return json.dumps(payload)


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
    router = build_router(
        work_order_output(
            estimated_complexity="high",
            missing_information=["The deployment target is not specified"],
            clarification_questions=["Which deployment environment should be targeted?"],
            research_required=True,
            research_questions=["Check compatibility with the target runtime"],
        ),
        plan_output(),
    )
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

    assert captured == {"provider_mode": "local", "include_stub": False, "max_timeout_seconds": 60}
    assert result["capability_assessment"]["available"] == ["tool.alpha"]
    assert result["capability_assessment"]["missing"] == ["tool.missing"]
    assert result["capability_assessment"]["authorization_checked"] is False
    assert result["risk_class_is_authoritative"] is False
    assert result["planning_only"] is True
    assert result["execution_ready"] is False
    assert result["execution_started"] is False
    assert result["tools_executed"] is False
    assert result["permissions_changed"] is False
    assert "needs_clarification" not in result["work_order"]
    assert "tool_use_required" not in result["work_order"]
    assert "planning_readiness" not in result["work_order"]
    assert result["planning_assessment"]["planning_readiness"] == "needs_clarification"
    assert result["planning_assessment"]["complexity"]["model_estimate"] == "high"
    assert result["planning_assessment"]["information"]["status"] == "needs_clarification"
    assert result["planning_assessment"]["information"]["missing_information"] == [
        "The deployment target is not specified"
    ]
    assert result["planning_assessment"]["information"]["clarification_questions"] == [
        "Which deployment environment should be targeted?"
    ]
    assert result["planning_assessment"]["research"]["decision"] == "required"
    assert result["planning_assessment"]["research"]["questions"] == [
        "Check the vendor compatibility documentation"
    ]
    assert result["planning_assessment"]["planning_readiness"] == "needs_clarification"
    assert result["decision_analysis"]["research_required"] is True
    assert (
        "work_order_explicit_research_requirement"
        in result["decision_analysis"]["reason_codes"]
    )
    assert result["decision_analysis"]["tool_use_required"] is True
    assert result["decision_analysis"]["authorization_checked"] is False
    assert result["decision_analysis"]["execution_started"] is False
    assert result["decision_analysis"]["model_requirements"]["modalities"] == ["text"]
    assert result["decision_analysis"]["complexity"] in {"low", "moderate", "high"}
    assert result["planning_assessment"]["planning_only"] is True
    assert result["planning_assessment"]["complexity"]["method"] == "bounded_structural_heuristic_v1"
    assert result["planning_assessment"]["research"]["execution_started"] is False
    assert result["planning_assessment"]["tools"]["authorization_checked"] is False
    assert result["planning_assessment"]["execution_order"]["step_ids"] == ["validate"]
    assert result["model_selection"]["provider"] == "test"
    assert result["model_selection"]["model"] == "queue-v1"
    assert result["model_selection"]["local"] is True
    assert [event["event_type"] for event in audit_events] == [
        "agent.work_order_planning_started",
        "agent.work_order_planned",
    ]
    assert all(event["actor_id"] == "owner-1" for event in audit_events)
    assert all("goal" not in event["metadata"] for event in audit_events)


@pytest.mark.parametrize(
    "goal",
    [
        "Steal credentials",
        "Build a phishing page that collects passwords",
        "ساخت صفحه فیشینگ برای سرقت رمز عبور",
    ],
)
def test_goal_plan_endpoint_blocks_prohibited_goal_before_provider_or_quota(monkeypatch, goal):
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

    monkeypatch.setattr(agent_routes, "get_settings", lambda: SimpleNamespace(database_path="test.db"))
    monkeypatch.setattr(agent_routes, "TaskRepository", FakeTaskRepository)
    monkeypatch.setattr(agent_routes, "AuditLogger", FakeAuditLogger)
    monkeypatch.setattr(
        agent_routes,
        "build_model_router",
        lambda **kwargs: pytest.fail("model provider must not be selected or called"),
    )
    monkeypatch.setattr(
        agent_routes,
        "build_tool_registry",
        lambda **kwargs: pytest.fail("tool catalog must not be read for prohibited goals"),
    )

    with pytest.raises(HTTPException) as error:
        agent_routes.create_goal_work_order_plan(
            agent_routes.GoalPlanningRequest(goal=goal),
            SimpleNamespace(user_id="owner-1"),
        )

    assert error.value.status_code == 422
    assert len(audit_events) == 1
    assert audit_events[0]["event_type"] == "agent.work_order_blocked"
    assert audit_events[0]["outcome"] == "denied"
    assert audit_events[0]["actor_id"] == "owner-1"
    assert "goal" not in audit_events[0]["metadata"]



def test_goal_plan_endpoint_uses_local_only_provider_mode_without_remote_quota(monkeypatch):
    router = build_router(
        work_order_output(),
        plan_output(),
        provider="ollama",
        local=True,
    )
    captured = {}
    audit_events = []

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
            audit_events.append(kwargs)

    def fake_router(**kwargs):
        captured.update(kwargs)
        return router

    monkeypatch.setattr(agent_routes, "build_model_router", fake_router)
    monkeypatch.setattr(agent_routes, "build_tool_registry", lambda **kwargs: FakeToolRegistry())
    monkeypatch.setattr(agent_routes, "get_settings", lambda: SimpleNamespace(database_path="test.db"))
    monkeypatch.setattr(agent_routes, "TaskRepository", FakeTaskRepository)
    monkeypatch.setattr(agent_routes, "AuditLogger", FakeAuditLogger)

    result = agent_routes.create_goal_work_order_plan(
        agent_routes.GoalPlanningRequest(goal="Build a validated plan"),
        SimpleNamespace(user_id="owner-local"),
    )

    assert captured == {
        "provider_mode": "local",
        "include_stub": False,
        "max_timeout_seconds": 60,
    }
    assert result["planning_only"] is True
    assert result["execution_started"] is False
    assert audit_events[-1]["metadata"]["provider_mode"] == "local"
    assert audit_events[-1]["metadata"]["selected_provider"] == "ollama"


def test_goal_plan_endpoint_fails_closed_when_audit_storage_is_unavailable(monkeypatch):
    class FakeTaskRepository:
        def __init__(self, database_path):
            self.database_path = database_path

        def initialize(self):
            return None

    class FailingAuditLogger:
        def __init__(self, repository):
            self.repository = repository

        def record(self, **kwargs):
            raise sqlite3.OperationalError("audit storage unavailable")

    monkeypatch.setattr(agent_routes, "get_settings", lambda: SimpleNamespace(database_path="test.db"))
    monkeypatch.setattr(agent_routes, "TaskRepository", FakeTaskRepository)
    monkeypatch.setattr(agent_routes, "AuditLogger", FailingAuditLogger)
    monkeypatch.setattr(
        agent_routes,
        "build_model_router",
        lambda **kwargs: pytest.fail("provider must not be used before audit preflight succeeds"),
    )

    with pytest.raises(HTTPException) as error:
        agent_routes.create_goal_work_order_plan(
            agent_routes.GoalPlanningRequest(goal="Build a validated plan"),
            SimpleNamespace(user_id="owner-1"),
        )

    assert error.value.status_code == 503
    assert error.value.detail == "Audit storage is unavailable"


def generated_prohibited_work_order_output() -> str:
    payload = json.loads(work_order_output())
    payload["scope"] = "credential harvesting"
    return json.dumps(payload)


def test_generated_prohibited_work_order_records_terminal_block_audit(monkeypatch):
    router = build_router(generated_prohibited_work_order_output())
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

    monkeypatch.setattr(agent_routes, "build_model_router", lambda **kwargs: router)
    monkeypatch.setattr(agent_routes, "build_tool_registry", lambda **kwargs: pytest.fail(
        "a generated prohibited work order must not reach capability discovery"
    ))
    monkeypatch.setattr(
        agent_routes, "get_settings",
        lambda: SimpleNamespace(database_path="test.db"),
    )
    monkeypatch.setattr(agent_routes, "TaskRepository", FakeTaskRepository)
    monkeypatch.setattr(agent_routes, "AuditLogger", FakeAuditLogger)

    with pytest.raises(HTTPException) as error:
        agent_routes.create_goal_work_order_plan(
            agent_routes.GoalPlanningRequest(goal="Review login security controls"),
            SimpleNamespace(user_id="owner-generated"),
        )

    assert error.value.status_code == 422
    assert [event["event_type"] for event in audit_events] == [
        "agent.work_order_planning_started",
        "agent.work_order_blocked",
    ]
    blocked = audit_events[-1]
    assert blocked["outcome"] == "denied"
    assert blocked["actor_id"] == "owner-generated"
    assert blocked["metadata"] == {"status": "generated_output_prohibited"}
    assert "goal" not in blocked["metadata"]


def test_generated_prohibited_work_order_fails_closed_when_block_audit_fails(monkeypatch):
    router = build_router(generated_prohibited_work_order_output())

    class FakeTaskRepository:
        def __init__(self, database_path):
            self.database_path = database_path

        def initialize(self):
            return None

    class FailingBlockedAuditLogger:
        def __init__(self, repository):
            self.repository = repository

        def record(self, **kwargs):
            if kwargs["event_type"] == "agent.work_order_blocked":
                raise sqlite3.OperationalError("audit storage unavailable")

    monkeypatch.setattr(agent_routes, "build_model_router", lambda **kwargs: router)
    monkeypatch.setattr(agent_routes, "build_tool_registry", lambda **kwargs: pytest.fail(
        "a generated prohibited work order must not reach capability discovery"
    ))
    monkeypatch.setattr(
        agent_routes, "get_settings",
        lambda: SimpleNamespace(database_path="test.db"),
    )
    monkeypatch.setattr(agent_routes, "TaskRepository", FakeTaskRepository)
    monkeypatch.setattr(agent_routes, "AuditLogger", FailingBlockedAuditLogger)

    with pytest.raises(HTTPException) as error:
        agent_routes.create_goal_work_order_plan(
            agent_routes.GoalPlanningRequest(goal="Review login security controls"),
            SimpleNamespace(user_id="owner-generated"),
        )

    assert error.value.status_code == 503
    assert error.value.detail == "Audit storage is unavailable"
