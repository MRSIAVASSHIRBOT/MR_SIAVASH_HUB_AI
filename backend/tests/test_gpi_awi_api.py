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
        "Check compatibility with the target runtime"
    ]
    assert result["decision_analysis"]["research_required"] is True
    assert result["decision_analysis"]["tool_use_required"] is True
    assert result["decision_analysis"]["authorization_checked"] is False
    assert result["decision_analysis"]["execution_started"] is False
    assert result["planning_assessment"]["planning_only"] is True
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
        "decision_analysis": {"complexity": "low", "research_required": False},
        "planning_assessment": {"readiness": "ready_for_review", "execution_ready": False},
        "model_selection": {
            "provider": "local-test",
            "model": "planner-test",
            "local": True,
            "rationale": "test-only local selection",
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
        "decision_analysis": payload_result["decision_analysis"],
        "planning_assessment": payload_result["planning_assessment"],
        "model_selection": payload_result["model_selection"],
    }
    assert result["decision_analysis"] == payload_result["decision_analysis"]
    assert result["planning_assessment"] == payload_result["planning_assessment"]
    assert result["model_selection"] == payload_result["model_selection"]


def test_persisted_plan_read_checks_owner_and_validates_encrypted_content(monkeypatch):
    from datetime import UTC, datetime
    from uuid import UUID, uuid4

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
        "decision_analysis": {"complexity": "moderate", "research_required": True},
        "planning_assessment": {"readiness": "needs_research", "execution_ready": False},
        "model_selection": {
            "provider": "local-test",
            "model": "planner-test",
            "local": True,
            "rationale": "test-only local selection",
        },
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
        UUID(plan_id),
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
    # Recompute advisory assessments from the validated plan and current server-side
    # capability catalog; persisted summary objects are not trusted as live assessments.
    expected_analysis = agent_routes.analyze_goal(
        work_order.goal,
        work_order=work_order,
    ).model_dump(mode="json")
    expected_capabilities = agent_routes.assess_work_order_capabilities(
        work_order,
        [{"name": "tool.alpha"}],
    )
    expected_planning_assessment = agent_routes.assess_work_order_intelligence(
        work_order,
        plan,
        expected_capabilities,
    ).as_dict()
    assert result["decision_analysis"] == expected_analysis
    assert result["planning_assessment"] == expected_planning_assessment
    assert result["decision_analysis"] != payload["decision_analysis"]
    assert result["planning_assessment"] != payload["planning_assessment"]
    assert result["model_selection"] == payload["model_selection"]
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


def test_persisted_plan_read_rejects_digest_mismatch_before_registry_use(monkeypatch):
    from datetime import UTC, datetime
    from uuid import UUID, uuid4

    owner = "owner-digest"
    plan_id = str(uuid4())
    key = b"p" * 32
    work_order = WorkOrder(
        goal="Review the registered capability",
        intent="Review only",
        required_capabilities=["tool.alpha"],
        acceptance_criteria=["The plan digest is checked"],
        verification_steps=["Recompute the canonical digest"],
        risk_class=RiskClass.LOW,
    )
    plan = ExecutionPlan(
        rationale="One review step",
        steps=[
            PlanStep(
                step_id="review",
                description="Review the persisted plan",
                required_capabilities=["tool.alpha"],
                verifies_criteria=["The plan digest is checked"],
                verification="Compare the canonical digest",
            )
        ],
    )
    payload = {
        "work_order": work_order.model_dump(mode="json"),
        "plan": plan.model_dump(mode="json"),
    }
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
        plan_digest="0" * 64,
        envelope=envelope,
        created_at=datetime(2026, 11, 22, tzinfo=UTC).isoformat(),
        expires_at=datetime(2026, 11, 22, 20, 15, tzinfo=UTC).isoformat(),
    )

    class FakeTaskRepository:
        def __init__(self, database_path):
            self.database_path = database_path

        def initialize(self):
            return None

    class FakePlanRepository:
        def __init__(self, database_path):
            self.database_path = database_path

        def get(self, requested_plan_id, *, owner_user_id):
            assert requested_plan_id == plan_id
            assert owner_user_id == owner
            return record

    monkeypatch.setattr(
        agent_routes,
        "get_settings",
        lambda: SimpleNamespace(database_path="test.db"),
    )
    monkeypatch.setattr(agent_routes, "TaskRepository", FakeTaskRepository)
    monkeypatch.setattr(agent_routes, "AgentWorkOrderPlanRepository", FakePlanRepository)
    monkeypatch.setattr(agent_routes, "load_payload_key", lambda: key)
    monkeypatch.setattr(
        agent_routes,
        "build_tool_registry",
        lambda **_kwargs: pytest.fail("registry must not be read after digest failure"),
    )

    with pytest.raises(HTTPException) as error:
        agent_routes.get_persisted_goal_work_order_plan(
            UUID(plan_id),
            SimpleNamespace(user_id=owner),
            Response(),
        )

    assert error.value.status_code == 409
    assert error.value.detail == "Plan record failed integrity or schema validation"


def test_persisted_plan_read_returns_gone_for_expired_records_before_decryption(monkeypatch):
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
            assert owner_user_id == "owner-expired"
            return SimpleNamespace(status="expired")

    monkeypatch.setattr(
        agent_routes,
        "get_settings",
        lambda: SimpleNamespace(database_path="test.db"),
    )
    monkeypatch.setattr(agent_routes, "TaskRepository", FakeTaskRepository)
    monkeypatch.setattr(agent_routes, "AgentWorkOrderPlanRepository", FakePlanRepository)
    monkeypatch.setattr(
        agent_routes,
        "load_payload_key",
        lambda: pytest.fail("expired records must not be decrypted"),
    )

    with pytest.raises(HTTPException) as error:
        agent_routes.get_persisted_goal_work_order_plan(
            uuid4(),
            SimpleNamespace(user_id="owner-expired"),
            Response(),
        )

    assert error.value.status_code == 410

def test_persisted_plan_revoke_is_owner_scoped_and_returns_no_store_headers(monkeypatch):
    from uuid import uuid4

    plan_id = uuid4()
    revoke_calls = []

    class FakeTaskRepository:
        def __init__(self, database_path):
            self.database_path = database_path

        def initialize(self):
            return None

    class FakePlanRepository:
        def __init__(self, database_path):
            self.database_path = database_path

        def revoke(self, requested_id, *, owner_user_id):
            revoke_calls.append((requested_id, owner_user_id))
            return SimpleNamespace(plan_id=requested_id, status="revoked")

    audit_events = []

    class FakeAuditLogger:
        def __init__(self, repository):
            self.repository = repository

        def record(self, **kwargs):
            audit_events.append(kwargs)

    monkeypatch.setattr(
        agent_routes,
        "get_settings",
        lambda: SimpleNamespace(database_path="test.db"),
    )
    monkeypatch.setattr(agent_routes, "TaskRepository", FakeTaskRepository)
    monkeypatch.setattr(agent_routes, "AgentWorkOrderPlanRepository", FakePlanRepository)
    monkeypatch.setattr(agent_routes, "AuditLogger", FakeAuditLogger)

    response = Response()
    result = agent_routes.revoke_persisted_goal_work_order_plan(
        plan_id,
        SimpleNamespace(user_id="owner-revoke"),
        response,
    )

    assert revoke_calls == [(str(plan_id), "owner-revoke")]
    assert audit_events == [{
        "event_type": "agent.work_order_plan_revocation_requested",
        "outcome": "requested",
        "actor_type": "user",
        "actor_id": "owner-revoke",
        "subject_type": "agent_work_order_plan",
        "subject_id": str(plan_id),
        "metadata": {"status": "revocation_requested", "decision": "revoke"},
    }]
    assert result == {
        "plan_id": str(plan_id),
        "status": "revoked",
        "revoked": True,
        "ciphertext_erased": True,
        "execution_started": False,
        "tools_executed": False,
    }
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["pragma"] == "no-cache"
    assert response.headers["x-content-type-options"] == "nosniff"


def test_persisted_plan_revoke_hides_records_owned_by_another_user(monkeypatch):
    from uuid import uuid4

    class FakeTaskRepository:
        def __init__(self, database_path):
            self.database_path = database_path

        def initialize(self):
            return None

    class FakePlanRepository:
        def __init__(self, database_path):
            self.database_path = database_path

        def revoke(self, _plan_id, *, owner_user_id):
            assert owner_user_id == "owner-foreign"

    monkeypatch.setattr(
        agent_routes,
        "get_settings",
        lambda: SimpleNamespace(database_path="test.db"),
    )
    monkeypatch.setattr(agent_routes, "TaskRepository", FakeTaskRepository)
    monkeypatch.setattr(agent_routes, "AgentWorkOrderPlanRepository", FakePlanRepository)
    monkeypatch.setattr(
        agent_routes, "AuditLogger",
        lambda _repository: SimpleNamespace(record=lambda **_kwargs: None),
    )

    with pytest.raises(HTTPException) as error:
        agent_routes.revoke_persisted_goal_work_order_plan(
            uuid4(),
            SimpleNamespace(user_id="owner-foreign"),
            Response(),
        )

    assert error.value.status_code == 404


def test_persisted_plan_revoke_returns_gone_for_expired_records(monkeypatch):
    from uuid import uuid4

    class FakeTaskRepository:
        def __init__(self, database_path):
            self.database_path = database_path

        def initialize(self):
            return None

    class FakePlanRepository:
        def __init__(self, database_path):
            self.database_path = database_path

        def revoke(self, _plan_id, *, owner_user_id):
            assert owner_user_id == "owner-expired-revoke"
            return SimpleNamespace(status="expired")

    monkeypatch.setattr(
        agent_routes,
        "get_settings",
        lambda: SimpleNamespace(database_path="test.db"),
    )
    monkeypatch.setattr(agent_routes, "TaskRepository", FakeTaskRepository)
    monkeypatch.setattr(agent_routes, "AgentWorkOrderPlanRepository", FakePlanRepository)
    monkeypatch.setattr(
        agent_routes, "AuditLogger",
        lambda _repository: SimpleNamespace(record=lambda **_kwargs: None),
    )

    with pytest.raises(HTTPException) as error:
        agent_routes.revoke_persisted_goal_work_order_plan(
            uuid4(),
            SimpleNamespace(user_id="owner-expired-revoke"),
            Response(),
        )

    assert error.value.status_code == 410

def test_persisted_plan_revoke_fails_closed_when_audit_storage_is_unavailable(monkeypatch):
    from uuid import uuid4

    class FakeTaskRepository:
        def __init__(self, database_path):
            self.database_path = database_path

        def initialize(self):
            return None

    class FailingAuditLogger:
        def __init__(self, repository):
            self.repository = repository

        def record(self, **_kwargs):
            raise sqlite3.OperationalError("audit storage unavailable")

    class MustNotRevokeRepository:
        def __init__(self, database_path):
            self.database_path = database_path

        def revoke(self, *_args, **_kwargs):
            pytest.fail("plan mutation must not run when the audit write fails")

    monkeypatch.setattr(
        agent_routes,
        "get_settings",
        lambda: SimpleNamespace(database_path="test.db"),
    )
    monkeypatch.setattr(agent_routes, "TaskRepository", FakeTaskRepository)
    monkeypatch.setattr(agent_routes, "AuditLogger", FailingAuditLogger)
    monkeypatch.setattr(
        agent_routes,
        "AgentWorkOrderPlanRepository",
        MustNotRevokeRepository,
    )

    with pytest.raises(HTTPException) as error:
        agent_routes.revoke_persisted_goal_work_order_plan(
            uuid4(),
            SimpleNamespace(user_id="owner-audit-failure"),
            Response(),
        )

    assert error.value.status_code == 503
    assert error.value.detail == "Audit storage is unavailable"



# Telegram integration GPI/AWI contract regression coverage.

def _telegram_work_order_output(**overrides: object) -> str:
    payload: dict[str, object] = {
        "intent": "Prepare a reviewable proposal",
        "scope": "Planning only",
        "assumptions": [],
        "constraints": ["No execution or external side effects"],
        "dependencies": [],
        "required_capabilities": ["tool.alpha"],
        "estimated_complexity": "low",
        "missing_information": [],
        "clarification_questions": [],
        "research_required": False,
        "research_questions": [],
        "acceptance_criteria": [
            "The proposal has a bounded structure",
            "Every criterion has a verification step",
        ],
        "verification_steps": [
            "Validate the proposal schema",
            "Inspect the criterion coverage",
        ],
    }
    payload.update(overrides)
    return json.dumps(payload)


def _telegram_plan_output(*, step_count: int = 2) -> str:
    steps = [
        {
            "step_id": "outline",
            "description": "Prepare the bounded proposal",
            "depends_on": [],
            "required_capabilities": ["tool.alpha"],
            "verifies_criteria": ["The proposal has a bounded structure"],
            "verification": "Validate the proposal schema",
        },
        {
            "step_id": "review",
            "description": "Review the proposal coverage",
            "depends_on": ["outline"],
            "required_capabilities": [],
            "verifies_criteria": ["Every criterion has a verification step"],
            "verification": "Inspect the criterion coverage",
        },
    ]
    return json.dumps({"rationale": "A bounded proposal with explicit checks", "steps": steps[:step_count]})


class FakeTelegramPlanningRouter:
    def __init__(self, outputs: list[str], *, local: bool = True) -> None:
        self.outputs = list(outputs)
        self.local = local
        self.generate_calls = 0
        self.selection_calls = 0

    def select(self, _request):
        self.selection_calls += 1
        return SimpleNamespace(
            provider="test-local" if self.local else "test-remote",
            model="test-planner-v1",
            local=self.local,
        )

    def generate(self, _request, _provider_request):
        self.generate_calls += 1
        return SimpleNamespace(output_text=self.outputs.pop(0))


def _configure_telegram_plan_preview(monkeypatch, outputs: list[str], *, local: bool = True):
    from mrhub.api.routes import telegram_integration as telegram_routes

    router = FakeTelegramPlanningRouter(outputs, local=local)
    captured: dict[str, object] = {}
    audit_events: list[dict[str, object]] = []

    class FakeAuditLogger:
        def __init__(self, repository):
            self.repository = repository

        def record(self, **kwargs):
            audit_events.append(kwargs)

    def fake_build_model_router(**kwargs):
        captured.update(kwargs)
        return router

    monkeypatch.setattr(telegram_routes, "build_model_router", fake_build_model_router)
    monkeypatch.setattr(telegram_routes, "_tasks_repository", lambda: object())
    monkeypatch.setattr(telegram_routes, "AuditLogger", FakeAuditLogger)
    return telegram_routes, router, captured, audit_events


def test_telegram_plan_preview_returns_versioned_gpi_awi_contract_and_legacy_steps(monkeypatch):
    from uuid import uuid4

    telegram_routes, router, captured, audit_events = _configure_telegram_plan_preview(
        monkeypatch,
        [_telegram_work_order_output(), _telegram_plan_output()],
    )
    identity = SimpleNamespace(owner_user_id="owner-telegram", client_id=uuid4())
    result = telegram_routes.preview_telegram_agent_plan(
        telegram_routes.TelegramAgentPlanPreviewRequest(
            goal="Prepare a reviewable proposal",
            provider_mode="local",
        ),
        identity,
    )

    contract = result["plan_contract"]
    assert contract["contract_version"] == "telegram_agent_plan.v1"
    assert contract["planning_status"] == "ready_for_review"
    assert contract["evaluation_scope"] == "planning_only"
    assert contract["goal_satisfaction"] == "not_evaluated"
    assert contract["capability_availability"] == "not_assessed"
    assert contract["authorization_checked"] is False
    assert contract["risk_class_is_authoritative"] is False
    assert contract["acceptance_criteria"] == [
        {"criterion_id": "ac_001", "statement": "The proposal has a bounded structure"},
        {"criterion_id": "ac_002", "statement": "Every criterion has a verification step"},
    ]
    assert contract["steps"][0]["verifies_criteria"] == ["ac_001"]
    assert contract["steps"][1]["verifies_criteria"] == ["ac_002"]
    assert contract["steps"][1]["depends_on"] == ["outline"]
    assert contract["execution_ready"] is False
    assert contract["execution_started"] is False
    assert contract["tools_executed"] is False
    assert contract["tasks_created"] == 0

    # Compatibility for existing EL_AI clients: the old description-only field remains.
    assert result["steps"] == [
        {"description": "Prepare the bounded proposal"},
        {"description": "Review the proposal coverage"},
    ]
    assert result["execution_started"] is False
    assert result["tasks_created"] == 0
    assert captured == {
        "provider_mode": "local",
        "include_stub": False,
        "max_timeout_seconds": 20.0,
    }
    assert router.selection_calls == 1
    assert router.generate_calls == 2
    assert router.outputs == []
    assert audit_events[-1]["event_type"] == "telegram.agent_plan_previewed"
    assert audit_events[-1]["metadata"]["contract_version"] == "telegram_agent_plan.v1"
    assert audit_events[-1]["metadata"]["tasks_created"] == 0
    assert "goal" not in audit_events[-1]["metadata"]


def test_telegram_plan_preview_requires_clarification_before_execution(monkeypatch):
    from uuid import uuid4

    telegram_routes, router, _captured, _audit_events = _configure_telegram_plan_preview(
        monkeypatch,
        [
            _telegram_work_order_output(
                missing_information=["The required target environment is unknown"],
                clarification_questions=["Which target environment should be used?"],
                research_required=True,
                research_questions=["Check current target environment requirements"],
            ),
            _telegram_plan_output(),
        ],
    )
    result = telegram_routes.preview_telegram_agent_plan(
        telegram_routes.TelegramAgentPlanPreviewRequest(
            goal="Prepare a reviewable proposal",
        ),
        SimpleNamespace(owner_user_id="owner-clarify", client_id=uuid4()),
    )

    contract = result["plan_contract"]
    assert contract["planning_status"] == "needs_clarification"
    assert contract["missing_information"] == [
        "The required target environment is unknown"
    ]
    assert contract["clarification_questions"] == [
        "Which target environment should be used?"
    ]
    assert contract["research_required"] is True
    assert contract["research_questions"] == [
        "Check current target environment requirements"
    ]
    assert contract["execution_ready"] is False
    assert contract["tasks_created"] == 0
    assert router.generate_calls == 2


def test_telegram_remote_plan_preview_applies_remote_quota_once(monkeypatch):
    from uuid import uuid4

    telegram_routes, router, captured, _audit_events = _configure_telegram_plan_preview(
        monkeypatch,
        [_telegram_work_order_output(), _telegram_plan_output()],
        local=False,
    )
    quota_owners: list[str] = []
    monkeypatch.setattr(
        telegram_routes,
        "_enforce_kimi_request_limit",
        lambda owner_id: quota_owners.append(owner_id),
    )
    result = telegram_routes.preview_telegram_agent_plan(
        telegram_routes.TelegramAgentPlanPreviewRequest(
            goal="Prepare a reviewable proposal",
            provider_mode="remote",
        ),
        SimpleNamespace(owner_user_id="owner-remote", client_id=uuid4()),
    )

    assert captured["provider_mode"] == "kimi"
    # One Kimi rate-limit reservation for GPI and one for AWI.
    assert quota_owners == ["owner-remote", "owner-remote"]
    assert router.generate_calls == 2
    assert result["provider"] == "test-remote"
    assert result["plan_contract"]["execution_started"] is False


def test_telegram_plan_preview_blocks_prohibited_goal_before_provider_selection(monkeypatch):
    from uuid import uuid4

    from mrhub.api.routes import telegram_integration as telegram_routes

    audit_events: list[dict[str, object]] = []
    client_id = uuid4()

    class FakeAuditLogger:
        def __init__(self, repository):
            self.repository = repository

        def record(self, **kwargs):
            audit_events.append(kwargs)

    monkeypatch.setattr(telegram_routes, "_tasks_repository", lambda: object())
    monkeypatch.setattr(telegram_routes, "AuditLogger", FakeAuditLogger)
    monkeypatch.setattr(
        telegram_routes,
        "derive_server_risk_class",
        lambda *_args, **_kwargs: RiskClass.PROHIBITED,
    )
    monkeypatch.setattr(
        telegram_routes,
        "build_model_router",
        lambda **_kwargs: pytest.fail("prohibited goals must be blocked before provider selection"),
    )

    with pytest.raises(HTTPException) as error:
        telegram_routes.preview_telegram_agent_plan(
            telegram_routes.TelegramAgentPlanPreviewRequest(
                goal="A prohibited request",
                provider_mode="remote",
            ),
            SimpleNamespace(owner_user_id="owner-blocked", client_id=client_id),
        )

    assert error.value.status_code == 422
    assert audit_events == [{
        "event_type": "telegram.agent_plan_blocked",
        "outcome": "denied",
        "subject_type": "agent_plan",
        "actor_type": "telegram_client",
        "actor_id": client_id,
        "metadata": {
            "status": "blocked",
            "declared_risk_class": RiskClass.PROHIBITED.value,
            "tasks_created": 0,
        },
    }]


def test_telegram_plan_preview_rejects_plans_outside_two_to_eight_steps(monkeypatch):
    from uuid import uuid4

    telegram_routes, router, _captured, _audit_events = _configure_telegram_plan_preview(
        monkeypatch,
        [_telegram_work_order_output(), _telegram_plan_output(step_count=1)],
    )

    with pytest.raises(HTTPException) as error:
        telegram_routes.preview_telegram_agent_plan(
            telegram_routes.TelegramAgentPlanPreviewRequest(
                goal="Prepare a reviewable proposal",
            ),
            SimpleNamespace(owner_user_id="owner-bounds", client_id=uuid4()),
        )

    assert error.value.status_code == 502
    assert error.value.detail == "The planning provider returned an invalid plan or work order."
    assert router.generate_calls == 2


def test_telegram_plan_preview_rejects_duplicate_acceptance_criteria(monkeypatch):
    from uuid import uuid4

    duplicated = _telegram_work_order_output(
        acceptance_criteria=[
            "The proposal has a bounded structure",
            "The proposal has a bounded structure",
        ],
    )
    telegram_routes, router, _captured, _audit_events = _configure_telegram_plan_preview(
        monkeypatch,
        [duplicated],
    )
    with pytest.raises(HTTPException) as error:
        telegram_routes.preview_telegram_agent_plan(
            telegram_routes.TelegramAgentPlanPreviewRequest(
                goal="Prepare a reviewable proposal",
            ),
            SimpleNamespace(owner_user_id="owner-duplicate", client_id=uuid4()),
        )

    assert error.value.status_code == 502
    assert router.generate_calls == 1


def test_telegram_plan_preview_rejects_non_topological_dependencies(monkeypatch):
    from uuid import uuid4

    plan = json.loads(_telegram_plan_output())
    plan["steps"][0]["depends_on"] = ["review"]
    plan["steps"][1]["depends_on"] = []
    telegram_routes, router, _captured, _audit_events = _configure_telegram_plan_preview(
        monkeypatch,
        [_telegram_work_order_output(), json.dumps(plan)],
    )

    with pytest.raises(HTTPException) as error:
        telegram_routes.preview_telegram_agent_plan(
            telegram_routes.TelegramAgentPlanPreviewRequest(
                goal="Prepare a reviewable proposal",
            ),
            SimpleNamespace(owner_user_id="owner-forward-dependency", client_id=uuid4()),
        )

    assert error.value.status_code == 502
    assert "invalid plan" in error.value.detail.lower()
    assert router.generate_calls == 2


def test_telegram_plan_preview_rejects_duplicate_criterion_references_per_step(monkeypatch):
    from uuid import uuid4

    plan = json.loads(_telegram_plan_output())
    plan["steps"][0]["verifies_criteria"] = [
        "The proposal has a bounded structure",
        "The proposal has a bounded structure",
    ]
    telegram_routes, router, _captured, _audit_events = _configure_telegram_plan_preview(
        monkeypatch,
        [_telegram_work_order_output(), json.dumps(plan)],
    )

    with pytest.raises(HTTPException) as error:
        telegram_routes.preview_telegram_agent_plan(
            telegram_routes.TelegramAgentPlanPreviewRequest(
                goal="Prepare a reviewable proposal",
            ),
            SimpleNamespace(owner_user_id="owner-duplicate-reference", client_id=uuid4()),
        )

    assert error.value.status_code == 502
    assert "invalid plan" in error.value.detail.lower()
    assert router.generate_calls == 2


def test_telegram_plan_preview_publishes_versioned_response_schema_in_openapi():
    from mrhub.main import create_app

    schema = create_app().openapi()
    operation = schema["paths"]["/integrations/telegram/agent/plan-preview"]["post"]
    response_schema = operation["responses"]["200"]["content"]["application/json"]["schema"]
    assert response_schema["$ref"].endswith("/TelegramAgentPlanPreviewResponse")

    components = schema["components"]["schemas"]
    response_model = components["TelegramAgentPlanPreviewResponse"]
    properties = response_model["properties"]
    assert set(properties) == {
        "provider_mode",
        "provider",
        "model",
        "steps",
        "plan_contract",
        "execution_started",
        "tasks_created",
    }
    assert properties["steps"]["items"]["$ref"].endswith("/TelegramAgentPlanStep")
    assert properties["plan_contract"]["$ref"].endswith("/TelegramAgentPlanContract")

    plan_contract = components["TelegramAgentPlanContract"]["properties"]
    assert plan_contract["contract_version"]["enum"] == ["telegram_agent_plan.v1"]
    assert plan_contract["evaluation_scope"]["enum"] == ["planning_only"]
    assert plan_contract["goal_satisfaction"]["enum"] == ["not_evaluated"]
    assert plan_contract["authorization_checked"]["const"] is False
    assert plan_contract["execution_started"]["const"] is False
    assert plan_contract["tasks_created"]["const"] == 0
