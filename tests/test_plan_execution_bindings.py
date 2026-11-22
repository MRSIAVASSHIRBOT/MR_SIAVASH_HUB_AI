from pydantic import BaseModel, ConfigDict, Field

import pytest

from mrhub.agents.awi_planner import ExecutionPlan, PlanStep
from mrhub.agents.core import AgentPlanRequest, AgentToolRequest
from mrhub.agents.plan_execution import (
    PlanExecutionBindingError,
    execution_request_digest,
    tool_contract_digest,
    topological_plan_steps,
    validate_plan_execution_payload,
)
from mrhub.domain.tasks import RiskClass
from mrhub.tools.registry import ToolDefinition


class TextInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=20)


class TextInputV2(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=10)


class TextOutput(BaseModel):
    text: str


def _tool(input_model=TextInput):
    return ToolDefinition(
        name="text.echo",
        description="Return text unchanged",
        input_model=input_model,
        output_model=TextOutput,
        handler=lambda payload: {"text": payload.text},
        risk_class=RiskClass.LOW,
        external_side_effect=False,
    )


def _plan():
    criterion = "The output matches the supplied text"
    return ExecutionPlan(
        rationale="A single ordered read-only demonstration step",
        steps=[
            PlanStep(
                step_id="second",
                description="Check the supplied output",
                depends_on=["first"],
                required_capabilities=["text.echo"],
                verifies_criteria=[criterion],
                verification="Compare the returned text with the input",
            ),
            PlanStep(
                step_id="first",
                description="Echo the supplied text",
                required_capabilities=["text.echo"],
                verifies_criteria=[criterion],
                verification="The tool returns the input text unchanged",
            ),
        ],
    )


def test_topological_order_is_stable_and_respects_dependencies():
    ordered = topological_plan_steps(_plan())
    assert [step.step_id for step in ordered] == ["first", "second"]


def test_contract_digest_changes_when_registered_input_schema_changes():
    assert tool_contract_digest(_tool()) != tool_contract_digest(_tool(TextInputV2))


def test_execution_request_digest_binds_tool_schema_fingerprint():
    base = {
        "step_id": "echo",
        "tool_name": "text.echo",
        "payload": {"text": "hello"},
        "tool_contract_digest": "a" * 64,
    }
    changed = {**base, "tool_contract_digest": "b" * 64}

    first = execution_request_digest(
        plan_id="11111111-1111-4111-8111-111111111111",
        plan_digest="c" * 64,
        bindings=[base],
    )
    second = execution_request_digest(
        plan_id="11111111-1111-4111-8111-111111111111",
        plan_digest="c" * 64,
        bindings=[changed],
    )
    assert first != second


def test_worker_envelope_requires_exact_step_tool_and_payload_alignment():
    plan_id = "11111111-1111-4111-8111-111111111111"
    payload = {
        "format": "mrhub.awi-plan-execution.v1",
        "request": AgentPlanRequest(
            goal="Echo a short value",
            tools=[AgentToolRequest(name="text.echo", payload={"text": "hello"})],
        ).model_dump(mode="json"),
        "plan_binding": {
            "plan_id": plan_id,
            "plan_digest": "c" * 64,
            "step_bindings": [{
                "step_id": "echo",
                "tool_name": "text.echo",
                "tool_contract_digest": "a" * 64,
            }],
        },
    }

    request, binding = validate_plan_execution_payload(payload)
    assert request.tools[0].name == "text.echo"
    assert binding["step_bindings"][0]["step_id"] == "echo"

    mismatched = {
        **payload,
        "plan_binding": {
            **payload["plan_binding"],
            "step_bindings": [{
                **payload["plan_binding"]["step_bindings"][0],
                "tool_name": "other.tool",
            }],
        },
    }
    with pytest.raises(PlanExecutionBindingError, match="does not match"):
        validate_plan_execution_payload(mismatched)


@pytest.mark.parametrize(
    "bad_payload",
    [
        {"format": "mrhub.awi-plan-execution.v1"},
        {
            "format": "mrhub.awi-plan-execution.v1",
            "request": {"goal": "task", "tools": []},
            "plan_binding": {
                "plan_id": "invalid",
                "plan_digest": "c" * 64,
                "step_bindings": [],
            },
        },
        {
            "format": "mrhub.awi-plan-execution.v1",
            "request": {
                "goal": "task",
                "tools": [
                    {"name": "text.echo", "payload": {"text": "a"}},
                    {"name": "text.echo", "payload": {"text": "b"}},
                ],
            },
            "plan_binding": {
                "plan_id": "11111111-1111-4111-8111-111111111111",
                "plan_digest": "c" * 64,
                "step_bindings": [{
                    "step_id": "echo",
                    "tool_name": "text.echo",
                    "tool_contract_digest": "a" * 64,
                }],
            },
        },
    ],
)
def test_worker_envelope_rejects_malformed_or_unbounded_bindings(bad_payload):
    with pytest.raises(PlanExecutionBindingError):
        validate_plan_execution_payload(bad_payload)
