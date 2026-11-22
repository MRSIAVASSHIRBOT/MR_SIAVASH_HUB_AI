from uuid import uuid4

import pytest
from pydantic import BaseModel, ConfigDict

from mrhub.agents.awi_planner import ExecutionPlan, PlanStep
from mrhub.agents.plan_execution import (
    PLAN_EXECUTION_FORMAT,
    PlanExecutionBindingError,
    execution_request_digest,
    topological_plan_steps,
    tool_contract_digest,
    validate_plan_execution_payload,
)
from mrhub.agents.core import AgentPlanRequest, AgentToolRequest
from mrhub.domain.tasks import RiskClass
from mrhub.tools.registry import ToolDefinition


class EchoInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str


class EchoOutput(BaseModel):
    text: str


def _plan() -> ExecutionPlan:
    return ExecutionPlan(
        rationale="Validate each step before continuing",
        steps=[
            PlanStep(
                step_id="publish",
                description="Prepare a final result",
                depends_on=["review"],
                required_capabilities=["text.echo"],
                verifies_criteria=["The result is prepared"],
                verification="Check the returned value",
            ),
            PlanStep(
                step_id="review",
                description="Review the supplied text",
                required_capabilities=["text.echo"],
                verifies_criteria=["The source is reviewed"],
                verification="Check the text schema",
            ),
        ],
    )


def _tool() -> ToolDefinition:
    return ToolDefinition(
        name="text.echo",
        description="Return text unchanged",
        input_model=EchoInput,
        output_model=EchoOutput,
        handler=lambda value: {"text": value.text},
        risk_class=RiskClass.LOW,
        external_side_effect=False,
    )


def test_topological_plan_order_is_stable_and_honors_dependencies():
    plan = _plan()

    ordered = topological_plan_steps(plan)

    assert [step.step_id for step in ordered] == ["review", "publish"]


def test_execution_digest_ordering_uses_identical_plan_identity():
    plan_id = str(uuid4())
    bindings = [
        {
            "step_id": "publish",
            "tool_name": "text.echo",
            "payload": {"text": "publish"},
            "tool_contract_digest": "a" * 64,
        },
        {
            "step_id": "review",
            "tool_name": "text.echo",
            "payload": {"text": "review"},
            "tool_contract_digest": "a" * 64,
        },
    ]

    first = execution_request_digest(
        plan_id=plan_id,
        plan_digest="b" * 64,
        bindings=bindings,
    )
    second = execution_request_digest(
        plan_id=plan_id,
        plan_digest="b" * 64,
        bindings=list(reversed(bindings)),
    )
    assert first == second


def test_tool_contract_digest_changes_when_schema_or_policy_changes():
    definition = _tool()
    digest = tool_contract_digest(definition)

    changed_risk = ToolDefinition(
        name=definition.name,
        description=definition.description,
        input_model=definition.input_model,
        output_model=definition.output_model,
        handler=definition.handler,
        risk_class=RiskClass.MEDIUM,
        external_side_effect=False,
    )
    assert digest != tool_contract_digest(changed_risk)


def test_worker_payload_requires_exact_binding_shape_and_matching_tool_order():
    plan_id = str(uuid4())
    digest = "c" * 64
    definition = _tool()
    request = AgentPlanRequest(
        goal="Review a short text",
        requires_text=True,
        requires_tool_calling=False,
        tools=[
            AgentToolRequest(name="text.echo", payload={"text": "review"}),
            AgentToolRequest(name="text.echo", payload={"text": "publish"}),
        ],
    )
    payload = {
        "format": PLAN_EXECUTION_FORMAT,
        "request": request.model_dump(mode="json"),
        "plan_binding": {
            "plan_id": plan_id,
            "plan_digest": digest,
            "step_bindings": [
                {
                    "step_id": "review",
                    "tool_name": "text.echo",
                    "tool_contract_digest": tool_contract_digest(definition),
                },
                {
                    "step_id": "publish",
                    "tool_name": "text.echo",
                    "tool_contract_digest": tool_contract_digest(definition),
                },
            ],
        },
    }

    validated_request, binding = validate_plan_execution_payload(payload)

    assert len(validated_request.tools) == 2
    assert binding["plan_id"] == plan_id


def test_worker_payload_rejects_mismatched_tool_order_and_duplicate_steps():
    plan_id = str(uuid4())
    definition = _tool()
    request = AgentPlanRequest(
        goal="Review a short text",
        tools=[
            AgentToolRequest(name="text.echo", payload={"text": "one"}),
            AgentToolRequest(name="text.echo", payload={"text": "two"}),
        ],
    )
    payload = {
        "format": PLAN_EXECUTION_FORMAT,
        "request": request.model_dump(mode="json"),
        "plan_binding": {
            "plan_id": plan_id,
            "plan_digest": "d" * 64,
            "step_bindings": [
                {
                    "step_id": "review",
                    "tool_name": "other.tool",
                    "tool_contract_digest": tool_contract_digest(definition),
                },
                {
                    "step_id": "review",
                    "tool_name": "text.echo",
                    "tool_contract_digest": tool_contract_digest(definition),
                },
            ],
        },
    }

    with pytest.raises(PlanExecutionBindingError):
        validate_plan_execution_payload(payload)


def test_worker_payload_rejects_unknown_envelope_fields():
    with pytest.raises(PlanExecutionBindingError):
        validate_plan_execution_payload(
            {
                "format": PLAN_EXECUTION_FORMAT,
                "request": {},
                "plan_binding": {},
                "client_approved": True,
            }
        )
