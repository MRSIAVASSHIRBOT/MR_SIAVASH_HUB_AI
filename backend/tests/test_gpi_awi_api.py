"""Authenticated GPI/AWI planning route tests."""

import json
import sqlite3
from types import SimpleNamespace

import pytest
from fastapi import HTTPException, Response

from mrhub.agents.awi_planner import ExecutionPlan, PlanStep
from mrhub.agents.work_order import WorkOrder
from mrhub.api.routes import agent as agent_routes
from mrhub.domain.tasks import RiskClass
from mrhub.jobs.payload_envelope import PayloadEnvelopeError, encrypt_plan_payload
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

    assert captured == {"include_stub": False, "max_timeout_seconds": 60}
    assert result["capability_assessment"]["available"] == ["tool.alpha"]
    assert result["capability_assessment"]["missing"] == ["tool.missing"]
    assert result["capability_assessment"]["authorization_checked"] is False
    assert result["risk_class_is_authoritative"] is False
    assert result["planning_only"] is True
    assert result["execution_ready"] is False
    assert result["execution_started"] is False
    assert result["tools_executed"] is False
    assert result["permissions_changed"] is False
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
        "_enforce_kimi_request_limit",
        lambda *_args, **_kwargs: pytest.fail("provider quota must not be consumed"),
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

    # Work-order generation and AWI planning each issue one remote model request.
    assert limited_owners == ["owner-remote", "owner-remote"]



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



def test_goal_plan_endpoint_stops_before_remote_inference_when_rate_limited(monkeypatch):
    router = build_router(
        work_order_output(),
        plan_output(),
        provider="moonshot",
        local=False,
    )
    provider = router.registry.get("moonshot", "queue-v1")

    def reject_remote_request(_owner_id):
        raise HTTPException(status_code=429, detail="rate limited")

    class FakeTaskRepository:
        def __init__(self, database_path):
            self.database_path = database_path

        def initialize(self):
            return None

        def record_audit(self, event):
            return None

    monkeypatch.setattr(agent_routes, "get_settings", lambda: SimpleNamespace(database_path="test.db"))
    monkeypatch.setattr(agent_routes, "TaskRepository", FakeTaskRepository)
    monkeypatch.setattr(agent_routes, "build_model_router", lambda **kwargs: router)
    monkeypatch.setattr(agent_routes, "_enforce_kimi_request_limit", reject_remote_request)

    with pytest.raises(HTTPException) as error:
        agent_routes.create_goal_work_order_plan(
            agent_routes.GoalPlanningRequest(goal="Build a validated plan"),
            SimpleNamespace(user_id="owner-remote"),
        )

    assert error.value.status_code == 429
    assert provider.calls == 0


def test_persisted_plan_endpoint_fails_before_inference_without_encryption_key(monkeypatch):
    class FakeTaskRepository:
        def __init__(self, database_path):
            self.database_path = database_path

        def initialize(self):
            return None

    monkeypatch.setattr(agent_routes, "get_settings", lambda: SimpleNamespace(database_path="test.db"))
    monkeypatch.setattr(agent_routes, "TaskRepository", FakeTaskRepository)
    monkeypatch.setattr(
        agent_routes,
        "load_payload_key",
        lambda: (_ for _ in ()).throw(PayloadEnvelopeError("missing key")),
    )
    monkeypatch.setattr(
        agent_routes,
        "create_goal_work_order_plan",
        lambda *_args, **_kwargs: pytest.fail("model inference must not start without the plan key"),
    )

    with pytest.raises(HTTPException) as error:
        agent_routes.create_persisted_goal_work_order_plan(
            agent_routes.PersistedGoalPlanningRequest(goal="Create a bounded plan"),
            SimpleNamespace(user_id="owner-1"),
            Response(),
        )

    assert error.value.status_code == 503


def test_persisted_plan_endpoint_encrypts_and_stores_the_plan(monkeypatch):
    key = b"p" * 32
    owner = "owner-1"
    plan_id_holder = {}
    payload_result = {
        "work_order": {
            "goal": "Create a bounded plan",
            "intent": "Create a bounded plan for review",
            "scope": "Planning only",
            "assumptions": [],
            "constraints": ["No execution"],
            "dependencies": [],
            "required_capabilities": ["tool.alpha"],
            "acceptance_criteria": ["The plan is validated"],
            "verification_steps": ["Review the plan"],
            "risk_class": "low",
        },
        "plan": {
            "rationale": "A single bounded step",
            "steps": [{
                "step_id": "review",
                "description": "Review the declared scope",
                "depends_on": [],
                "required_capabilities": ["tool.alpha"],
                "verifies_criteria": ["The plan is validated"],
                "verification": "Check the plan schema",
            }],
        },
        "capability_assessment": {
            "required": ["tool.alpha"],
            "available": ["tool.alpha"],
            "missing": [],
            "complete": True,
            "authorization_checked": False,
        },
    }

    class FakeTaskRepository:
        def __init__(self, database_path):
            self.database_path = database_path

        def initialize(self):
            return None

    class FakePlanRepository:
        def __init__(self, database_path):
            self.database_path = database_path

        def create(self, **kwargs):
            plan_id_holder.update(kwargs)
            from datetime import UTC, datetime, timedelta

            now = datetime(2026, 11, 22, 20, 0, tzinfo=UTC)
            return SimpleNamespace(
                plan_id=kwargs["plan_id"],
                status="active",
                plan_digest=kwargs["plan_digest"],
                created_at=now.isoformat(),
                expires_at=(now + timedelta(seconds=kwargs["ttl_seconds"])).isoformat(),
            )

    monkeypatch.setattr(agent_routes, "get_settings", lambda: SimpleNamespace(database_path="test.db"))
    monkeypatch.setattr(agent_routes, "TaskRepository", FakeTaskRepository)
    monkeypatch.setattr(agent_routes, "AgentWorkOrderPlanRepository", FakePlanRepository)
    monkeypatch.setattr(agent_routes, "load_payload_key", lambda: key)
    monkeypatch.setattr(
        agent_routes,
        "create_goal_work_order_plan",
        lambda *_args, **_kwargs: payload_result,
    )

    response = Response()
    result = agent_routes.create_persisted_goal_work_order_plan(
        agent_routes.PersistedGoalPlanningRequest(
            goal="Create a bounded plan",
            expires_in_seconds=600,
        ),
        SimpleNamespace(user_id=owner),
        response,
    )

    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["pragma"] == "no-cache"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert result["status"] == "active"
    assert result["planning_only"] is True
    assert result["execution_ready"] is False
    assert result["execution_started"] is False
    assert result["tools_executed"] is False
    assert result["permissions_changed"] is False
    assert plan_id_holder["owner_user_id"] == owner
    assert plan_id_holder["ttl_seconds"] == 600
    assert plan_id_holder["envelope"].ciphertext_b64 != str(payload_result)
    decrypted = agent_routes.decrypt_plan_payload(
        plan_id_holder["envelope"],
        plan_id=plan_id_holder["plan_id"],
        owner_user_id=owner,
        key=key,
    )
    assert decrypted == {
        "work_order": payload_result["work_order"],
        "plan": payload_result["plan"],
    }


def test_persisted_plan_read_checks_owner_and_validates_encrypted_content(monkeypatch):
    from datetime import UTC, datetime
    from uuid import uuid4

    owner = "owner-1"
    plan_id = str(uuid4())
    key = b"p" * 32
    work_order = WorkOrder(
        goal="Inspect the registered tool list",
        intent="Inspect only",
        required_capabilities=["tool.alpha"],
        acceptance_criteria=["The registry presence is reported"],
        verification_steps=["Validate the stored plan"],
        risk_class=RiskClass.LOW,
    )
    plan = ExecutionPlan(
        rationale="One bounded review step",
        steps=[
            PlanStep(
                step_id="review",
                description="Review the declared capability",
                required_capabilities=["tool.alpha"],
                verifies_criteria=["The registry presence is reported"],
                verification="Check the exact tool name",
            )
        ],
    )
    payload = {
        "work_order": work_order.model_dump(mode="json"),
        "plan": plan.model_dump(mode="json"),
    }
    plan_digest = agent_routes._canonical_plan_digest(payload)
    envelope = encrypt_plan_payload(
        payload,
        plan_id=plan_id,
        owner_user_id=owner,
        key=key,
    )
    record = SimpleNamespace(
        plan_id=plan_id,
        owner_user_id=owner,
        status="active",
        plan_digest=plan_digest,
        envelope=envelope,
        created_at=datetime(2026, 11, 22, tzinfo=UTC).isoformat(),
        expires_at=datetime(2026, 11, 22, 20, 15, tzinfo=UTC).isoformat(),
    )
    repository_calls = []

    class FakeTaskRepository:
        def __init__(self, database_path):
            self.database_path = database_path

        def initialize(self):
            return None

    class FakePlanRepository:
        def __init__(self, database_path):
            self.database_path = database_path

        def get(self, requested_plan_id, *, owner_user_id):
            repository_calls.append((requested_plan_id, owner_user_id))
            return record if requested_plan_id == plan_id and owner_user_id == owner else None

    class FakeToolRegistry:
        def catalog(self):
            return [{"name": "tool.alpha"}]

    monkeypatch.setattr(agent_routes, "get_settings", lambda: SimpleNamespace(database_path="test.db"))
    monkeypatch.setattr(agent_routes, "TaskRepository", FakeTaskRepository)
    monkeypatch.setattr(agent_routes, "AgentWorkOrderPlanRepository", FakePlanRepository)
    monkeypatch.setattr(agent_routes, "load_payload_key", lambda: key)
    monkeypatch.setattr(agent_routes, "build_tool_registry", lambda **_kwargs: FakeToolRegistry())

    response = Response()
    result = agent_routes.get_persisted_goal_work_order_plan(
        uuid4(),
        SimpleNamespace(user_id=owner),
        response,
    )

    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["pragma"] == "no-cache"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert repository_calls == [(plan_id, owner)]
    assert result["plan_id"] == plan_id
    assert result["work_order"]["goal"] == work_order.goal
    assert result["plan"]["steps"][0]["step_id"] == "review"
    assert result["capability_assessment"]["available"] == ["tool.alpha"]
    assert result["capability_assessment"]["authorization_checked"] is False
    assert result["planning_only"] is True
    assert result["execution_started"] is False


def test_persisted_plan_read_hides_records_owned_by_another_user(monkeypatch):
    from uuid import uuid4

    class FakeTaskRepository:
        def __init__(self, database_path):
            self.database_path = database_path

        def initialize(self):
            return None

    class FakePlanRepository:
        def __init__(self, database_path):
            self.database_path = database_path

        def get(self, _plan_id, *, owner_user_id):
            assert owner_user_id == "owner-2"
            return None

    monkeypatch.setattr(agent_routes, "get_settings", lambda: SimpleNamespace(database_path="test.db"))
    monkeypatch.setattr(agent_routes, "TaskRepository", FakeTaskRepository)
    monkeypatch.setattr(agent_routes, "AgentWorkOrderPlanRepository", FakePlanRepository)

    with pytest.raises(HTTPException) as error:
        agent_routes.get_persisted_goal_work_order_plan(
            uuid4(),
            SimpleNamespace(user_id="owner-2"),
            Response(),
        )

    assert error.value.status_code == 404
