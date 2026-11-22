from uuid import uuid4

import pytest
from pydantic import BaseModel, ConfigDict, Field

from mrhub.agents.awi_planner import ExecutionPlan, PlanStep
from mrhub.agents.core import AgentPlanRequest
from mrhub.agents.plan_execution import (
    PLAN_EXECUTION_FORMAT,
    PlanExecutionBindingError,
    canonical_digest,
    execution_request_digest,
    tool_contract_digest,
    topological_plan_steps,
    validate_plan_bindings_against_snapshot,
    validate_plan_execution_payload,
)
from mrhub.agents.work_order import WorkOrder
from mrhub.domain.tasks import RiskClass
from mrhub.security.policy import PolicyDecision
from mrhub.tools.registry import ToolDefinition, ToolRegistry


class EchoInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=200)


class EchoOutput(BaseModel):
    text: str
    character_count: int


def make_work_order(*, risk_class=RiskClass.LOW, capabilities=None):
    return WorkOrder(
        goal="Review the supplied text safely",
        intent="Validate a low-risk tool binding",
        scope="No external effects",
        assumptions=[],
        constraints=["No external side effects"],
        dependencies=[],
        required_capabilities=capabilities or ["text.echo"],
        acceptance_criteria=["The typed request is validated"],
        verification_steps=["Check the registered schema"],
        risk_class=risk_class,
    )


def make_plan(*, capabilities=None, depends_on=None):
    capability_list = capabilities or ["text.echo"]
    return ExecutionPlan(
        rationale="Bind each plan step to one exact registered tool",
        steps=[
            PlanStep(
                step_id="review",
                description="Validate the tool input",
                depends_on=depends_on or [],
                required_capabilities=[capability_list[0]],
                verifies_criteria=["The typed request is validated"],
                verification="Validate the exact input model",
            )
        ],
    )


def make_registry(*, external_side_effect=False, risk_class=RiskClass.LOW, permissions=frozenset()):
    calls = []

    def handler(value):
        calls.append(value.model_dump(mode="json"))
        return {"text": value.text, "character_count": len(value.text)}

    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="text.echo",
            description="Return the supplied text without external effects.",
            input_model=EchoInput,
            output_model=EchoOutput,
            handler=handler,
            risk_class=risk_class,
            required_permissions=permissions,
            external_side_effect=external_side_effect,
        )
    )
    return registry, calls


def make_execution_request():
    return AgentPlanRequest(
        goal="Review the supplied text safely",
        tools=[{"name": "text.echo", "payload": {"text": "hello"}}],
    )


def make_binding(registry, *, contract_digest=None):
    definition = registry.get("text.echo")
    return {
        "plan_id": str(uuid4()),
        "plan_digest": "a" * 64,
        "request_digest": "c" * 64,
        "step_bindings": [
            {
                "step_id": "review",
                "tool_name": "text.echo",
                "tool_contract_digest": contract_digest or tool_contract_digest(definition),
            }
        ],
    }


def test_plan_binding_validates_exact_capability_schema_and_policy_without_invoking_handler():
    registry, calls = make_registry()
    request = make_execution_request()
    work_order = make_work_order()
    plan = make_plan()
    binding = make_binding(registry)

    validate_plan_bindings_against_snapshot(
        request=request,
        binding=binding,
        work_order=work_order,
        plan=plan,
        registry=registry,
        granted_permissions=frozenset(),
    )

    assert calls == []
    assert registry.evaluate_policy("text.echo").decision is PolicyDecision.ALLOW


@pytest.mark.parametrize(
    ("registry_options", "permissions", "message"),
    [
        ({"external_side_effect": True}, frozenset(), "without external side effects"),
        ({"risk_class": RiskClass.HIGH}, frozenset(), "without external side effects"),
        ({"permissions": frozenset({"text.echo.read"})}, frozenset(), "policy do not allow"),
    ],
)
def test_plan_binding_fails_closed_for_unsafe_or_unauthorized_tools(
    registry_options,
    permissions,
    message,
):
    registry, calls = make_registry(**registry_options)
    request = make_execution_request()
    binding = make_binding(registry)

    with pytest.raises(PlanExecutionBindingError, match=message):
        validate_plan_bindings_against_snapshot(
            request=request,
            binding=binding,
            work_order=make_work_order(),
            plan=make_plan(),
            registry=registry,
            granted_permissions=permissions,
        )

    assert calls == []


def test_plan_binding_rejects_high_risk_work_order_even_for_low_risk_tool():
    registry, calls = make_registry()
    with pytest.raises(PlanExecutionBindingError, match="low-risk work orders"):
        validate_plan_bindings_against_snapshot(
            request=make_execution_request(),
            binding=make_binding(registry),
            work_order=make_work_order(risk_class=RiskClass.HIGH),
            plan=make_plan(),
            registry=registry,
            granted_permissions=frozenset(),
        )
    assert calls == []


def test_plan_binding_rejects_tool_schema_drift_before_handler_invocation():
    registry, calls = make_registry()
    with pytest.raises(PlanExecutionBindingError, match="contract has changed"):
        validate_plan_bindings_against_snapshot(
            request=make_execution_request(),
            binding=make_binding(registry, contract_digest="0" * 64),
            work_order=make_work_order(),
            plan=make_plan(),
            registry=registry,
            granted_permissions=frozenset(),
        )
    assert calls == []


def test_plan_binding_rejects_noncanonical_payload_and_extra_fields():
    registry, calls = make_registry()
    request = AgentPlanRequest(
        goal="Review the supplied text safely",
        tools=[{"name": "text.echo", "payload": {"text": "hello", "admin": True}}],
    )
    with pytest.raises(PlanExecutionBindingError, match="schema validation"):
        validate_plan_bindings_against_snapshot(
            request=request,
            binding=make_binding(registry),
            work_order=make_work_order(),
            plan=make_plan(),
            registry=registry,
            granted_permissions=frozenset(),
        )
    assert calls == []


def test_topological_order_is_stable_and_dependency_first():
    plan = ExecutionPlan(
        rationale="Stable dependency ordering",
        steps=[
            PlanStep(
                step_id="publish",
                description="Second step",
                depends_on=["prepare"],
                required_capabilities=["text.echo"],
                verifies_criteria=["The typed request is validated"],
                verification="Check second step",
            ),
            PlanStep(
                step_id="prepare",
                description="First step",
                depends_on=[],
                required_capabilities=["text.echo"],
                verifies_criteria=["The typed request is validated"],
                verification="Check first step",
            ),
        ],
    )
    assert [step.step_id for step in topological_plan_steps(plan)] == [
        "prepare",
        "publish",
    ]


def test_worker_payload_requires_exact_format_binding_schema():
    request = make_execution_request()
    payload = {
        "format": PLAN_EXECUTION_FORMAT,
        "request": request.model_dump(mode="json"),
        "plan_binding": make_binding(make_registry()[0]),
    }
    parsed, binding = validate_plan_execution_payload(payload)
    assert parsed == request
    assert binding["plan_id"] == payload["plan_binding"]["plan_id"]

    payload["unexpected"] = True
    with pytest.raises(PlanExecutionBindingError, match="envelope shape"):
        validate_plan_execution_payload(payload)


def test_execution_request_digest_is_stable_and_binds_every_payload_field():
    bindings = [
        {"step_id": "review", "tool_name": "text.echo", "payload": {"text": "one"}}
    ]
    plan_id = str(uuid4())
    digest = execution_request_digest(
        plan_id=plan_id,
        plan_digest="b" * 64,
        bindings=bindings,
    )
    changed = execution_request_digest(
        plan_id=plan_id,
        plan_digest="b" * 64,
        bindings=[{"step_id": "review", "tool_name": "text.echo", "payload": {"text": "two"}}],
    )
    assert len(digest) == 64
    assert digest != changed


def test_canonical_digest_rejects_non_finite_json_values():
    with pytest.raises(PlanExecutionBindingError, match="finite JSON"):
        canonical_digest({"value": float("nan")})
