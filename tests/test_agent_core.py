import pytest
from pydantic import BaseModel

from mrhub.agents.core import AgentCore, AgentPlanRequest
from mrhub.domain.tasks import RiskClass
from mrhub.providers.router import ModelRouter
from mrhub.providers.stub import StubProvider
from mrhub.security.policy import PolicyDecision, PolicyEngine
from mrhub.tools.builtins import build_tool_registry
from mrhub.tools.registry import ToolDefinition


class EmptyInput(BaseModel):
    pass


class EmptyOutput(BaseModel):
    accepted: bool


def make_core():
    router = ModelRouter()
    router.register_provider(StubProvider())
    return AgentCore(router, build_tool_registry())


def test_agent_core_selects_provider_and_plans_registered_tool_without_execution():
    plan = make_core().plan(
        AgentPlanRequest(
            goal="Echo a short message",
            tools=[{"name": "text.echo", "payload": {"text": "hello"}}],
        )
    )
    assert plan["selected_provider"]["provider"] == "stub"
    assert plan["execution_ready"] is True
    assert plan["decision_mode"] == "plan_only"
    assert plan["model_inference_started"] is False
    assert plan["tools_executed"] is False
    assert plan["steps"][1]["status"] == "ready"


def test_agent_core_blocks_unknown_tools():
    plan = make_core().plan(
        AgentPlanRequest(
            goal="Request an unregistered tool",
            tools=[{"name": "missing.registered.tool", "payload": {}}],
        )
    )
    assert plan["execution_ready"] is False
    assert plan["steps"][1]["status"] == "not_registered"
    assert plan["steps"][1]["decision"] == PolicyDecision.DENY.value


def test_agent_core_marks_external_side_effect_for_approval():
    core = make_core()
    core.tool_registry.register(
        ToolDefinition(
            name="custom.external",
            description="External action",
            input_model=EmptyInput,
            output_model=EmptyOutput,
            handler=lambda _payload: {"accepted": True},
            risk_class=RiskClass.LOW,
            external_side_effect=True,
        )
    )
    plan = core.plan(
        AgentPlanRequest(
            goal="Plan external action",
            tools=[{"name": "custom.external", "payload": {}}],
        )
    )
    assert plan["execution_ready"] is False
    assert plan["steps"][1]["status"] == "approval_required"


def test_agent_core_marks_invalid_tool_input_without_running_it():
    plan = make_core().plan(
        AgentPlanRequest(
            goal="Echo invalid input",
            tools=[{"name": "text.echo", "payload": {"unexpected": "value"}}],
        )
    )
    assert plan["steps"][1]["status"] == "invalid_input"
    assert plan["tools_executed"] is False


def test_agent_core_rejects_unsupported_provider_capabilities():
    with pytest.raises(LookupError):
        make_core().plan(
            AgentPlanRequest(goal="Analyze image", requires_vision=True)
        )


def test_agent_execute_runs_registered_safe_tool():
    response = make_core().execute(
        AgentPlanRequest(
            goal="Echo safely",
            tools=[{"name": "text.echo", "payload": {"text": "hello"}}],
        )
    )
    assert response["execution_completed"] is True
    assert response["tools_executed"] is True
    assert response["model_inference_started"] is False
    assert response["results"][0]["result"]["character_count"] == 5


def test_agent_execute_does_not_start_when_plan_is_blocked():
    response = make_core().execute(
        AgentPlanRequest(
            goal="Block an unregistered action",
            tools=[
                {"name": "text.echo", "payload": {"text": "hello"}},
                {"name": "missing.registered.tool", "payload": {}},
            ],
        )
    )
    assert response["execution_started"] is False
    assert response["tools_executed"] is False
    assert response["blocked"] is True
    assert response["results"] == []


def test_agent_execute_requires_approval_for_external_tool():
    core = make_core()
    core.tool_registry.register(
        ToolDefinition(
            name="custom.external",
            description="External action",
            input_model=EmptyInput,
            output_model=EmptyOutput,
            handler=lambda _payload: {"accepted": True},
            risk_class=RiskClass.LOW,
            external_side_effect=True,
        )
    )
    response = core.execute(
        AgentPlanRequest(
            goal="External action needs approval",
            tools=[{"name": "custom.external", "payload": {}}],
        )
    )
    assert response["execution_started"] is False
    assert response["tools_executed"] is False
    assert response["blocked"] is True


def test_agent_execute_handles_policy_denial_during_invoke_revalidation():
    from mrhub.security.policy import PolicyResult
    from mrhub.tools.registry import ToolRegistry

    class RevalidatingPolicy(PolicyEngine):
        def __init__(self):
            self.calls = 0

        def evaluate(self, request):
            self.calls += 1
            if self.calls == 1:
                return PolicyResult(
                    decision=PolicyDecision.ALLOW,
                    reason="Allowed during planning",
                )
            return PolicyResult(
                decision=PolicyDecision.DENY,
                reason="Revoked before invocation",
            )

    policy = RevalidatingPolicy()
    registry = ToolRegistry(policy=policy)
    called = []
    registry.register(
        ToolDefinition(
            name="custom.policy_revalidation",
            description="Exercise policy revalidation between planning and invocation.",
            input_model=EmptyInput,
            output_model=EmptyOutput,
            handler=lambda _payload: called.append(True) or {"accepted": True},
        )
    )
    router = ModelRouter()
    router.register_provider(StubProvider())
    core = AgentCore(router, registry)
    events = []

    response = core.execute(
        AgentPlanRequest(
            goal="Verify policy revocation is enforced at invocation",
            tools=[{"name": "custom.policy_revalidation", "payload": {}}],
        ),
        on_step=lambda number, status, error: events.append((number, status, error)),
    )

    assert policy.calls == 2
    assert called == []
    assert response["execution_completed"] is False
    assert response["tools_executed"] is False
    assert response["blocked"] is True
    assert response["failed_tool"] == "custom.policy_revalidation"
    assert response["error_code"] == "policy_denied"
    assert events == [
        (2, "running", None),
        (2, "failed", "policy_denied"),
    ]


def test_agent_execute_stops_after_runtime_failure():
    core = make_core()
    core.tool_registry.register(
        ToolDefinition(
            name="custom.failure",
            description="Test failure handling",
            input_model=EmptyInput,
            output_model=EmptyOutput,
            handler=lambda _payload: (_ for _ in ()).throw(
                RuntimeError("private diagnostic detail")
            ),
        )
    )
    response = core.execute(
        AgentPlanRequest(
            goal="Stop on first tool error",
            tools=[
                {"name": "text.echo", "payload": {"text": "first"}},
                {"name": "custom.failure", "payload": {}},
                {"name": "text.echo", "payload": {"text": "must not run"}},
            ],
        )
    )
    assert response["execution_completed"] is False
    assert response["failed_tool"] == "custom.failure"
    assert response["error_code"] == "tool_execution_failed"
    assert "private diagnostic detail" not in str(response)
    assert len(response["results"]) == 1

def test_agent_execute_honors_cancellation_before_first_tool():
    response = make_core().execute(
        AgentPlanRequest(
            goal="Cancel before execution",
            tools=[{"name": "text.echo", "payload": {"text": "must not run"}}],
        ),
        should_cancel=lambda: True,
    )
    assert response["cancelled"] is True
    assert response["execution_completed"] is False
    assert response["results"] == []
    assert response["tools_executed"] is False


def test_agent_execute_stops_between_tools_after_cancellation():
    checks = 0

    def cancel_after_first_tool():
        nonlocal checks
        checks += 1
        return checks >= 2

    response = make_core().execute(
        AgentPlanRequest(
            goal="Stop between workflow steps",
            tools=[
                {"name": "text.echo", "payload": {"text": "first"}},
                {"name": "text.echo", "payload": {"text": "must not run"}},
            ],
        ),
        should_cancel=cancel_after_first_tool,
    )
    assert response["cancelled"] is True
    assert response["execution_completed"] is False
    assert len(response["results"]) == 1
    assert response["results"][0]["result"]["character_count"] == 5


class DenyEchoPolicy:
    """Policy test double that rejects the echo tool at the shared boundary."""

    def evaluate(self, request):
        from mrhub.security.policy import PolicyResult

        return PolicyResult(
            decision=PolicyDecision.DENY,
            reason="Test policy denies this tool",
        )


def test_agent_plan_uses_the_tool_registry_policy_authority():
    from mrhub.tools.registry import ToolRegistry

    policy = DenyEchoPolicy()
    registry = ToolRegistry(policy=policy)
    from mrhub.tools.builtins import EchoToolInput, EchoToolOutput

    registry.register(
        ToolDefinition(
            name="text.echo",
            description="Return text for a policy consistency test.",
            input_model=EchoToolInput,
            output_model=EchoToolOutput,
            handler=lambda payload: EchoToolOutput(
                text=payload.text, character_count=len(payload.text)
            ),
        )
    )
    router = ModelRouter()
    router.register_provider(StubProvider())
    core = AgentCore(router, registry)

    plan = core.plan(
        AgentPlanRequest(
            goal="Verify shared policy authority",
            tools=[{"name": "text.echo", "payload": {"text": "blocked"}}],
        )
    )

    assert plan["execution_ready"] is False
    assert plan["steps"][1]["decision"] == PolicyDecision.DENY.value
    response = core.execute(
        AgentPlanRequest(
            goal="Verify execution remains blocked",
            tools=[{"name": "text.echo", "payload": {"text": "blocked"}}],
        )
    )
    assert response["blocked"] is True
    assert response["tools_executed"] is False


def test_agent_core_rejects_a_split_policy_authority():
    from mrhub.tools.registry import ToolRegistry

    router = ModelRouter()
    router.register_provider(StubProvider())
    with pytest.raises(ValueError, match="same instance"):
        AgentCore(router, ToolRegistry(), policy=PolicyEngine())
