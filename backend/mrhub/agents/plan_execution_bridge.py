"""Safe bridge from reviewed AWI plans to the existing AgentPlanRequest contract."""

from __future__ import annotations

import re
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from mrhub.agents.awi_planner import ExecutionPlan
from mrhub.agents.core import AgentPlanRequest, AgentToolRequest
from mrhub.agents.gpi import derive_server_risk_class
from mrhub.agents.work_order import WorkOrder
from mrhub.agents.workflow_plan import WorkflowPlanError, WorkflowStep, build_workflow_plan
from mrhub.domain.tasks import RiskClass
from mrhub.security.policy import PolicyDecision
from mrhub.tools.registry import ToolRegistry

MAX_EXECUTABLE_PLAN_STEPS = 5
_STEP_ID_PATTERN = re.compile(r"^[a-z][a-z0-9-]{0,63}$")
_PLAN_ID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
_DIGEST_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class PlanExecutionBridgeError(ValueError):
    """Raised when a reviewed plan cannot be safely bound to registered tools."""


class PlanToolBinding(BaseModel):
    """One user-confirmed binding from an exact AWI step to a typed registered tool."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    step_id: str = Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9-]{0,63}$")
    tool_name: str = Field(min_length=1, max_length=80, pattern=r"^[a-z][a-z0-9_.-]{0,79}$")
    payload: dict[str, object] = Field(default_factory=dict)


def build_plan_execution_request(
    work_order: WorkOrder,
    plan: ExecutionPlan,
    bindings: list[PlanToolBinding],
    *,
    registry: ToolRegistry,
    granted_permissions: frozenset[str],
    plan_id: str,
    plan_digest: str,
) -> AgentPlanRequest:
    """Validate explicit step/tool/payload bindings and build a durable request.

    Descriptions and model-generated prose are never interpreted as tool
    arguments. Only exact registered names and schema-validated user payloads
    cross this boundary. Policy must return ALLOW; this v1 bridge does not
    manufacture or infer an approval record.
    """
    try:
        normalized_plan_id = str(UUID(plan_id))
    except (TypeError, ValueError, AttributeError) as exc:
        raise PlanExecutionBridgeError("Source plan identifier is invalid") from exc
    if normalized_plan_id != plan_id or not _PLAN_ID_PATTERN.fullmatch(plan_id):
        raise PlanExecutionBridgeError("Source plan identifier is not canonical")
    if not isinstance(plan_digest, str) or not _DIGEST_PATTERN.fullmatch(plan_digest):
        raise PlanExecutionBridgeError("Source plan digest is invalid")

    if derive_server_risk_class(
        work_order.goal,
        work_order.model_dump(mode="json"),
    ) is RiskClass.PROHIBITED:
        raise PlanExecutionBridgeError("Source goal is outside the supported safety policy")

    if len(plan.steps) > MAX_EXECUTABLE_PLAN_STEPS:
        raise PlanExecutionBridgeError(
            "Plans exceeding the five-step execution contract remain planning-only"
        )
    if len(bindings) != len(plan.steps):
        raise PlanExecutionBridgeError("Every plan step must have exactly one tool binding")

    criterion_ids = set(work_order.acceptance_criteria)
    planned_criteria = {
        criterion for step in plan.steps for criterion in step.verifies_criteria
    }
    if planned_criteria != criterion_ids:
        raise PlanExecutionBridgeError("Plan acceptance-criteria coverage is inconsistent")

    declared_capabilities = work_order.required_capabilities
    if len(declared_capabilities) != len(set(declared_capabilities)):
        raise PlanExecutionBridgeError("Work order repeats a required capability")
    planned_capabilities = {
        capability
        for step in plan.steps
        for capability in step.required_capabilities
    }
    if planned_capabilities != set(declared_capabilities):
        raise PlanExecutionBridgeError("Plan capability coverage is inconsistent")

    steps_by_id = {step.step_id: step for step in plan.steps}
    if len(steps_by_id) != len(plan.steps):
        raise PlanExecutionBridgeError("Plan step identifiers are duplicated")
    for step_id in steps_by_id:
        if not _STEP_ID_PATTERN.fullmatch(step_id):
            raise PlanExecutionBridgeError(
                "Plan step identity is not supported by the durable workflow contract"
            )

    binding_by_id: dict[str, PlanToolBinding] = {}
    for binding in bindings:
        if binding.step_id in binding_by_id:
            raise PlanExecutionBridgeError("A plan step has more than one binding")
        binding_by_id[binding.step_id] = binding
    if set(binding_by_id) != set(steps_by_id):
        raise PlanExecutionBridgeError("Tool bindings contain missing or unknown plan steps")

    try:
        dag = build_workflow_plan(
            [
                WorkflowStep(
                    step_id=step.step_id,
                    description=step.description,
                    depends_on=tuple(step.depends_on),
                )
                for step in plan.steps
            ]
        )
    except (WorkflowPlanError, TypeError) as exc:
        raise PlanExecutionBridgeError("Plan dependency graph is invalid") from exc

    ordered_tools: list[AgentToolRequest] = []
    for step in dag.ordered_steps:
        plan_step = steps_by_id[step.step_id]
        binding = binding_by_id[step.step_id]
        if len(plan_step.required_capabilities) != 1:
            raise PlanExecutionBridgeError(
                "Every executable plan step must declare exactly one capability"
            )
        exact_capability = plan_step.required_capabilities[0]
        if binding.tool_name != exact_capability:
            raise PlanExecutionBridgeError(
                "Tool name must exactly match the step's declared capability"
            )

        try:
            tool = registry.get(binding.tool_name)
            validated_input = tool.input_model.model_validate(binding.payload)
        except LookupError as exc:
            raise PlanExecutionBridgeError("A required tool is not registered") from exc
        except (TypeError, ValueError) as exc:
            raise PlanExecutionBridgeError("Tool input does not match its registered schema") from exc

        decision = registry.evaluate_policy(
            tool.name,
            granted_permissions=granted_permissions,
        )
        if decision.decision is not PolicyDecision.ALLOW:
            raise PlanExecutionBridgeError(
                "A required tool is not currently authorized by server policy"
            )

        ordered_tools.append(
            AgentToolRequest(
                name=tool.name,
                payload=validated_input.model_dump(mode="json"),
                step_id=step.step_id,
                depends_on=list(plan_step.depends_on),
                expected_schema_digest=registry.contract_digest(tool.name),
            )
        )

    try:
        return AgentPlanRequest(
            goal=work_order.goal,
            requires_text=True,
            requires_tool_calling=False,
            tools=ordered_tools,
            required_capabilities=sorted(set(declared_capabilities)),
            source_plan_id=plan_id,
            source_plan_digest=plan_digest,
        )
    except (TypeError, ValueError) as exc:
        raise PlanExecutionBridgeError(
            "Validated plan could not be represented by the durable workflow contract"
        ) from exc


def bindings_from_agent_request(request: AgentPlanRequest) -> list[PlanToolBinding]:
    """Reconstruct explicit bindings for worker-side revalidation against the source plan."""
    if request.source_plan_id is None or request.source_plan_digest is None:
        raise PlanExecutionBridgeError("Agent request is not linked to a persisted source plan")
    if any(tool.step_id is None or tool.depends_on is None for tool in request.tools):
        raise PlanExecutionBridgeError("AWI execution requests require explicit stable identities")
    return [
        PlanToolBinding(
            step_id=tool.step_id,
            tool_name=tool.name,
            payload=tool.payload,
        )
        for tool in request.tools
    ]
