import pytest
from pydantic import BaseModel, ValidationError

from mrhub.agents.core import AgentCore, AgentPlanRequest, AgentToolRequest
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
    assert plan["dependency_plan"]["dependency_levels"] == [
        ["step-1"],
        ["step-2"],
    ]


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


@pytest.mark.parametrize(
    ("revoked_decision", "expected_error"),
    [
        (PolicyDecision.DENY, "policy_denied"),
        (PolicyDecision.REQUIRE_APPROVAL, "approval_required"),
    ],
)
def test_agent_execute_handles_policy_denial_during_invoke_revalidation(
    revoked_decision, expected_error
):
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
                decision=revoked_decision,
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
    assert response["error_code"] == expected_error
    assert events == [
        (2, "running", None),
        (2, "failed", expected_error),
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


def test_agent_core_revalidates_owner_grants_before_each_tool_dispatch():
    from mrhub.tools.registry import ToolRegistry

    calls = []
    snapshots = [frozenset({"cloudflare.read"}), frozenset()]

    def permission_provider():
        return snapshots.pop(0)

    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="cloudflare.test_read",
            description="Read one test resource through an owner grant.",
            input_model=EmptyInput,
            output_model=EmptyOutput,
            handler=lambda _payload: calls.append("read") or {"accepted": True},
            required_permissions=frozenset({"cloudflare.read"}),
        )
    )
    router = ModelRouter()
    router.register_provider(StubProvider())
    core = AgentCore(router, registry, permission_provider=permission_provider)

    response = core.execute(
        AgentPlanRequest(
            goal="Read only while the owner grant remains active",
            tools=[{"name": "cloudflare.test_read", "payload": {}}],
        )
    )

    assert response["plan"]["execution_ready"] is True
    assert response["execution_completed"] is False
    assert response["blocked"] is True
    assert response["failed_tool"] == "cloudflare.test_read"
    assert response["error_code"] == "policy_denied"
    assert calls == []


def test_agent_core_executes_a_read_tool_with_a_live_owner_grant():
    from mrhub.tools.registry import ToolRegistry

    calls = []
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="cloudflare.test_read",
            description="Read one test resource through an owner grant.",
            input_model=EmptyInput,
            output_model=EmptyOutput,
            handler=lambda _payload: calls.append("read") or {"accepted": True},
            required_permissions=frozenset({"cloudflare.read"}),
        )
    )
    router = ModelRouter()
    router.register_provider(StubProvider())
    core = AgentCore(
        router,
        registry,
        permission_provider=lambda: frozenset({"cloudflare.read"}),
    )

    response = core.execute(
        AgentPlanRequest(
            goal="Read an owner-approved resource",
            tools=[{"name": "cloudflare.test_read", "payload": {}}],
        )
    )

    assert response["execution_completed"] is True
    assert response["results"][0]["result"]["accepted"] is True
    assert calls == ["read"]


def test_agent_core_fails_closed_when_owner_grant_lookup_fails():
    from mrhub.tools.registry import ToolRegistry

    calls = []
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="cloudflare.test_read",
            description="Read one test resource through an owner grant.",
            input_model=EmptyInput,
            output_model=EmptyOutput,
            handler=lambda _payload: calls.append("read") or {"accepted": True},
            required_permissions=frozenset({"cloudflare.read"}),
        )
    )
    router = ModelRouter()
    router.register_provider(StubProvider())

    def unavailable_permissions():
        raise RuntimeError("permission database unavailable")

    core = AgentCore(router, registry, permission_provider=unavailable_permissions)
    plan = core.plan(
        AgentPlanRequest(
            goal="Deny access when permission lookup is unavailable",
            tools=[{"name": "cloudflare.test_read", "payload": {}}],
        )
    )

    assert plan["execution_ready"] is False
    assert plan["steps"][1]["decision"] == PolicyDecision.DENY.value
    assert calls == []


@pytest.mark.parametrize(
    "ordered_steps",
    [
        [
            {"step_id": "step-1", "description": "Select provider", "depends_on": []},
            {"step_id": "step-2", "description": "First tool", "depends_on": ["step-1"]},
            {"step_id": "step-2", "description": "Duplicate tool", "depends_on": ["step-1"]},
        ],
        [
            {"step_id": "step-1", "description": "Select provider", "depends_on": []},
            {"step_id": "step-2", "description": "First tool", "depends_on": ["step-1"]},
        ],
    ],
    ids=["duplicate-tool-step", "missing-tool-step"],
)
def test_agent_execute_rejects_incomplete_or_duplicate_workflow_graph_before_invocation(
    monkeypatch, ordered_steps
):
    core = make_core()
    request = AgentPlanRequest(
        goal="Reject malformed workflow plans before invoking tools",
        tools=[
            {"name": "text.echo", "payload": {"text": "first"}},
            {"name": "text.echo", "payload": {"text": "second"}},
        ],
    )
    calls = []
    monkeypatch.setattr(
        core,
        "plan",
        lambda _request: {
            "execution_ready": True,
            "dependency_plan": {"ordered_steps": ordered_steps},
        },
    )
    monkeypatch.setattr(
        core.tool_registry,
        "invoke",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    with pytest.raises(RuntimeError, match="does not match request dependency declarations"):
        core.execute(request)

    assert calls == []


def test_agent_execute_resumes_from_the_requested_workflow_step():
    events = []
    response = make_core().execute(
        AgentPlanRequest(
            goal="Resume from the second tool step",
            tools=[
                {"name": "text.echo", "payload": {"text": "already completed"}},
                {"name": "text.echo", "payload": {"text": "resume here"}},
            ],
        ),
        start_step=3,
        on_step=lambda number, status, error: events.append((number, status, error)),
    )

    assert response["execution_completed"] is True
    assert [item["result"]["text"] for item in response["results"]] == ["resume here"]
    assert events == [(3, "running", None), (3, "succeeded", None)]


def test_agent_plan_reports_required_capability_coverage():
    plan = make_core().plan(
        AgentPlanRequest(
            goal="Check whether the requested capability is registered",
            tools=[{"name": "text.echo", "payload": {"text": "hello"}}],
            required_capabilities=["text.echo", "missing.lookup"],
        )
    )

    assert plan["capability_gaps"] == {
        "required": ["text.echo", "missing.lookup"],
        "available": ["text.echo"],
        "missing": ["missing.lookup"],
        "complete": False,
    }
    assert plan["execution_ready"] is False


def test_agent_execute_fails_closed_when_required_capabilities_are_missing():
    core = make_core()
    calls = []
    original_invoke = core.tool_registry.invoke

    def track_invoke(*args, **kwargs):
        calls.append(args[0])
        return original_invoke(*args, **kwargs)

    core.tool_registry.invoke = track_invoke
    response = core.execute(
        AgentPlanRequest(
            goal="Do not execute with an unresolved capability gap",
            tools=[{"name": "text.echo", "payload": {"text": "must not run"}}],
            required_capabilities=["filesystem.read"],
        )
    )

    assert response["blocked"] is True
    assert response["execution_started"] is False
    assert response["tools_executed"] is False
    assert response["plan"]["capability_gaps"]["missing"] == ["filesystem.read"]
    assert calls == []




def test_agent_plan_preserves_legacy_sequential_dependencies():
    request = AgentPlanRequest(
        goal="Preserve legacy sequential tool execution",
        tools=[
            {"name": "text.echo", "payload": {"text": "first"}},
            {"name": "text.echo", "payload": {"text": "second"}},
        ],
    )

    graph = make_core().plan(request)["dependency_plan"]

    assert graph["ordered_steps"] == [
        {
            "step_id": "step-1",
            "description": "Select the model provider",
            "depends_on": [],
        },
        {
            "step_id": "step-2",
            "description": "Execute registered tool: text.echo",
            "depends_on": ["step-1"],
        },
        {
            "step_id": "step-3",
            "description": "Execute registered tool: text.echo",
            "depends_on": ["step-2"],
        },
    ]


def test_agent_plan_supports_explicit_tool_dependency_order():
    request = AgentPlanRequest(
        goal="Run the second request tool before the first",
        tools=[
            {
                "name": "text.echo",
                "payload": {"text": "first-request-tool"},
                "depends_on": ["step-3"],
            },
            {
                "name": "text.echo",
                "payload": {"text": "second-request-tool"},
                "depends_on": [],
            },
        ],
    )

    plan = make_core().plan(request)

    assert plan["dependency_plan"]["ordered_steps"] == [
        {
            "step_id": "step-1",
            "description": "Select the model provider",
            "depends_on": [],
        },
        {
            "step_id": "step-3",
            "description": "Execute registered tool: text.echo",
            "depends_on": ["step-1"],
        },
        {
            "step_id": "step-2",
            "description": "Execute registered tool: text.echo",
            "depends_on": ["step-1", "step-3"],
        },
    ]


@pytest.mark.parametrize(
    "tools",
    [
        [
            {"name": "text.echo", "depends_on": ["step-6"]},
        ],
        [
            {"name": "text.echo", "depends_on": ["step-2"]},
        ],
        [
            {"name": "text.echo", "depends_on": ["step-3"]},
            {"name": "text.echo", "depends_on": ["step-2"]},
        ],
        [
            {"name": "text.echo", "depends_on": ["step-1", "step-1"]},
        ],
    ],
    ids=[
        "unknown-dependency",
        "self-dependency",
        "dependency-cycle",
        "duplicate-dependency",
    ],
)
def test_agent_plan_rejects_invalid_explicit_tool_dependencies(tools):
    with pytest.raises(ValidationError):
        AgentPlanRequest(
            goal="Reject malformed tool dependency declarations",
            tools=tools,
        )


def test_agent_plan_accepts_a_complete_registered_capability_set():
    plan = make_core().plan(
        AgentPlanRequest(
            goal="Check a fully registered capability set",
            tools=[{"name": "text.echo", "payload": {"text": "hello"}}],
            required_capabilities=["TEXT.ECHO"],
        )
    )

    assert plan["capability_gaps"]["complete"] is True
    assert plan["capability_gaps"]["missing"] == []
    assert plan["execution_ready"] is True



@pytest.mark.parametrize("name", ["", "   ", "x" * 81])
def test_agent_plan_rejects_blank_or_oversized_required_capability_names(name):
    with pytest.raises(ValidationError):
        AgentPlanRequest(
            goal="Validate capability request input",
            required_capabilities=[name],
        )


def test_agent_plan_normalizes_required_capability_names():
    request = AgentPlanRequest(
        goal="Normalize capability request input",
        required_capabilities=["  text.echo  "],
    )

    assert request.required_capabilities == ["text.echo"]


@pytest.mark.parametrize("goal", ["", "   "])
def test_agent_plan_rejects_blank_goal(goal):
    with pytest.raises(ValidationError):
        AgentPlanRequest(goal=goal)


def test_agent_plan_normalizes_goal():
    request = AgentPlanRequest(goal="  Review workflow state  ")
    assert request.goal == "Review workflow state"


@pytest.mark.parametrize("name", ["", "   "])
def test_agent_tool_request_rejects_blank_tool_name(name):
    with pytest.raises(ValidationError):
        AgentToolRequest(name=name)


def test_agent_tool_request_normalizes_tool_name():
    request = AgentToolRequest(name="  text.echo  ")
    assert request.name == "text.echo"


def test_agent_execute_follows_validated_dependency_graph_order(monkeypatch):
    core = make_core()
    request = AgentPlanRequest(
        goal="Execute tools in the declared dependency order",
        tools=[
            {
                "name": "text.echo",
                "payload": {"text": "first"},
                "depends_on": ["step-3"],
            },
            {
                "name": "text.echo",
                "payload": {"text": "second"},
                "depends_on": [],
            },
        ],
    )
    monkeypatch.setattr(
        core,
        "plan",
        lambda _request: {
            "execution_ready": True,
            "dependency_plan": {
                "ordered_steps": [
                    {
                        "step_id": "step-1",
                        "description": "Select the model provider",
                        "depends_on": [],
                    },
                    {
                        "step_id": "step-3",
                        "description": "Execute registered tool: text.echo",
                        "depends_on": ["step-1"],
                    },
                    {
                        "step_id": "step-2",
                        "description": "Execute registered tool: text.echo",
                        "depends_on": ["step-1", "step-3"],
                    },
                ],
                "dependency_levels": [["step-1"], ["step-3"], ["step-2"]],
            },
        },
    )
    events = []

    response = core.execute(
        request,
        on_step=lambda number, status, error: events.append((number, status, error)),
    )

    assert response["execution_completed"] is True
    assert [item["result"]["text"] for item in response["results"]] == [
        "second",
        "first",
    ]
    # Durable callback positions follow the topological execution order.
    assert events == [
        (2, "running", None),
        (2, "succeeded", None),
        (3, "running", None),
        (3, "succeeded", None),
    ]


def test_agent_execute_resumes_by_topological_position_not_request_index(monkeypatch):
    core = make_core()
    request = AgentPlanRequest(
        goal="Resume by durable topological execution position",
        tools=[
            {
                "name": "text.echo",
                "payload": {"text": "first-request-tool"},
                "depends_on": ["step-3"],
            },
            {
                "name": "text.echo",
                "payload": {"text": "second-request-tool"},
                "depends_on": [],
            },
        ],
    )
    monkeypatch.setattr(
        core,
        "plan",
        lambda _request: {
            "execution_ready": True,
            "dependency_plan": {
                "ordered_steps": [
                    {
                        "step_id": "step-1",
                        "description": "Select the model provider",
                        "depends_on": [],
                    },
                    {
                        "step_id": "step-3",
                        "description": "Execute second request tool",
                        "depends_on": ["step-1"],
                    },
                    {
                        "step_id": "step-2",
                        "description": "Execute first request tool",
                        "depends_on": ["step-1"],
                    },
                ],
                "dependency_levels": [["step-1"], ["step-3"], ["step-2"]],
            },
        },
    )
    events = []

    response = core.execute(
        request,
        start_step=3,
        on_step=lambda number, status, error: events.append((number, status, error)),
    )

    assert response["execution_completed"] is True
    assert [item["result"]["text"] for item in response["results"]] == [
        "first-request-tool"
    ]
    assert events == [(3, "running", None), (3, "succeeded", None)]


def test_agent_execute_rejects_non_topological_graph_before_invocation(monkeypatch):
    core = make_core()
    request = AgentPlanRequest(
        goal="Reject a graph whose order violates its dependencies",
        tools=[
            {
                "name": "text.echo",
                "payload": {"text": "first"},
                "depends_on": ["step-3"],
            },
            {
                "name": "text.echo",
                "payload": {"text": "second"},
                "depends_on": [],
            },
        ],
    )
    calls = []
    monkeypatch.setattr(
        core,
        "plan",
        lambda _request: {
            "execution_ready": True,
            "dependency_plan": {
                "ordered_steps": [
                    {
                        "step_id": "step-1",
                        "description": "Select provider",
                        "depends_on": [],
                    },
                    {
                        "step_id": "step-2",
                        "description": "Must wait for step 3",
                        "depends_on": ["step-3"],
                    },
                    {
                        "step_id": "step-3",
                        "description": "Prerequisite",
                        "depends_on": ["step-1"],
                    },
                ],
                "dependency_levels": [["step-1"], ["step-3"], ["step-2"]],
            },
        },
    )
    monkeypatch.setattr(
        core.tool_registry,
        "invoke",
        lambda *args, **kwargs: calls.append(args),
    )

    with pytest.raises(RuntimeError, match="does not match request dependency declarations"):
        core.execute(request)

    assert calls == []




def test_agent_execute_rejects_valid_graph_that_drops_a_declared_dependency(monkeypatch):
    core = make_core()
    request = AgentPlanRequest(
        goal="Do not silently remove a declared tool dependency",
        tools=[
            {
                "name": "text.echo",
                "payload": {"text": "must-run-second"},
                "depends_on": ["step-3"],
            },
            {
                "name": "text.echo",
                "payload": {"text": "must-run-first"},
                "depends_on": [],
            },
        ],
    )
    calls = []
    monkeypatch.setattr(
        core,
        "plan",
        lambda _request: {
            "execution_ready": True,
            "dependency_plan": {
                # This graph is internally valid and topologically ordered, but
                # it has dropped the request's step-2 -> step-3 dependency.
                "ordered_steps": [
                    {
                        "step_id": "step-1",
                        "description": "Select the model provider",
                        "depends_on": [],
                    },
                    {
                        "step_id": "step-2",
                        "description": "Execute registered tool: text.echo",
                        "depends_on": ["step-1"],
                    },
                    {
                        "step_id": "step-3",
                        "description": "Execute registered tool: text.echo",
                        "depends_on": ["step-1"],
                    },
                ],
                "dependency_levels": [["step-1"], ["step-2", "step-3"]],
            },
        },
    )
    monkeypatch.setattr(
        core.tool_registry,
        "invoke",
        lambda *args, **kwargs: calls.append(args),
    )

    with pytest.raises(
        RuntimeError, match="does not match request dependency declarations"
    ):
        core.execute(request)

    assert calls == []


def test_workflow_step_input_digest_binds_identity_payload_and_dependencies():
    first = AgentToolRequest(
        name="text.echo",
        payload={"text": "first"},
    )
    second = AgentToolRequest(
        name="text.echo",
        payload={"text": "second"},
    )
    same_payload_different_dependencies = AgentToolRequest(
        name="text.echo",
        payload={"text": "first"},
        depends_on=["step-3"],
    )

    first_digest = AgentCore.workflow_step_input_digest(2, first)
    second_digest = AgentCore.workflow_step_input_digest(3, second)
    dependency_digest = AgentCore.workflow_step_input_digest(
        2, same_payload_different_dependencies
    )

    assert len(first_digest) == 64
    assert len(second_digest) == 64
    assert first_digest != second_digest
    assert first_digest != dependency_digest
    assert first_digest == AgentCore.workflow_step_input_digest(2, first)


def test_agent_plan_request_canonical_payload_preserves_legacy_digest_shape():
    legacy_request = AgentPlanRequest(
        goal="Keep existing workflow request identity stable",
        tools=[{"name": "text.echo", "payload": {"text": "legacy"}}],
    )

    assert legacy_request.canonical_payload() == {
        "goal": "Keep existing workflow request identity stable",
        "requires_text": True,
        "requires_vision": False,
        "requires_audio": False,
        "requires_tool_calling": False,
        "prefer_local": False,
        "tools": [
            {
                "name": "text.echo",
                "payload": {"text": "legacy"},
            }
        ],
    }


def test_agent_plan_request_canonical_payload_omits_empty_cgi_capabilities():
    request = AgentPlanRequest(
        goal="Preserve pre-CGI workflow request identity",
        required_capabilities=[],
    )

    assert "required_capabilities" not in request.canonical_payload()


def test_agent_plan_request_canonical_payload_includes_nonempty_cgi_capabilities():
    request = AgentPlanRequest(
        goal="Include declared CGI requirements in the workflow identity",
        required_capabilities=["text.echo"],
    )

    assert request.canonical_payload()["required_capabilities"] == ["text.echo"]


def test_agent_plan_request_canonical_payload_includes_explicit_dependencies():
    request = AgentPlanRequest(
        goal="Include explicit dependencies in the request identity",
        tools=[
            {
                "name": "text.echo",
                "payload": {"text": "first"},
                "depends_on": ["step-3"],
            },
            {
                "name": "text.echo",
                "payload": {"text": "second"},
                "depends_on": [],
            },
        ],
    )

    assert request.canonical_payload()["tools"][0]["depends_on"] == ["step-3"]
    assert request.canonical_payload()["tools"][1]["depends_on"] == []


def test_agent_execute_follows_request_declared_dag_dependencies():
    core = make_core()
    request = AgentPlanRequest(
        goal="Execute explicit DAG dependencies in topological order",
        tools=[
            {
                "name": "text.echo",
                "payload": {"text": "first-request-tool"},
                "depends_on": ["step-3"],
            },
            {
                "name": "text.echo",
                "payload": {"text": "second-request-tool"},
                "depends_on": [],
            },
        ],
    )
    events = []

    response = core.execute(
        request,
        on_step=lambda number, status, error: events.append((number, status, error)),
    )

    assert response["execution_completed"] is True
    assert [item["result"]["text"] for item in response["results"]] == [
        "second-request-tool",
        "first-request-tool",
    ]
    assert events == [
        (2, "running", None),
        (2, "succeeded", None),
        (3, "running", None),
        (3, "succeeded", None),
    ]


def test_agent_execute_resumes_explicit_dag_by_durable_execution_position():
    events = []
    response = make_core().execute(
        AgentPlanRequest(
            goal="Resume the remaining step in an explicit DAG",
            tools=[
                {
                    "name": "text.echo",
                    "payload": {"text": "first-request-tool"},
                    "depends_on": ["step-3"],
                },
                {
                    "name": "text.echo",
                    "payload": {"text": "second-request-tool"},
                    "depends_on": [],
                },
            ],
        ),
        start_step=3,
        on_step=lambda number, status, error: events.append((number, status, error)),
    )

    assert response["execution_completed"] is True
    assert [item["result"]["text"] for item in response["results"]] == [
        "first-request-tool"
    ]
    assert events == [(3, "running", None), (3, "succeeded", None)]
