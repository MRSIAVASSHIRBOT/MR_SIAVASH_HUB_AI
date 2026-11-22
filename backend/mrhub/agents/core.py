"""Deterministic planning core connecting model routing, tools, and policy."""

import hashlib
import json
from collections.abc import Callable
from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from mrhub.agents.capability_gaps import MAX_NAME_LENGTH, evaluate_capability_gaps
from mrhub.agents.workflow_plan import WorkflowPlanError, WorkflowStep, build_workflow_plan
from mrhub.providers.router import ModelRequest, ModelRouter
from mrhub.security.policy import PolicyDecision, PolicyEngine
from mrhub.tools.registry import ToolExecutionError, ToolPolicyError, ToolRegistry


WorkflowDependencyId = Annotated[
    str, Field(min_length=6, max_length=6, pattern=r"^step-[2-6]$")
]


class AgentToolRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=80)
    payload: dict[str, object] = Field(default_factory=dict)
    # None preserves legacy sequential request order. An explicit list declares
    # dependencies on other request steps; provider selection is always implicit.
    depends_on: list[WorkflowDependencyId] | None = Field(default=None, max_length=5)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("tool name must not be blank")
        return normalized

    @field_validator("depends_on")
    @classmethod
    def reject_duplicate_dependencies(
        cls, dependencies: list[str] | None
    ) -> list[str] | None:
        if dependencies is not None and len(dependencies) != len(set(dependencies)):
            raise ValueError("tool dependencies must be unique")
        return dependencies


class AgentPlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    goal: str = Field(min_length=1, max_length=1000)
    requires_text: bool = True
    requires_vision: bool = False
    requires_audio: bool = False
    requires_tool_calling: bool = False
    prefer_local: bool = False
    tools: list[AgentToolRequest] = Field(default_factory=list, max_length=5)
    required_capabilities: list[str] = Field(default_factory=list, max_length=50)

    @field_validator("goal")
    @classmethod
    def normalize_goal(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("goal must not be blank")
        return normalized

    @field_validator("required_capabilities")
    @classmethod
    def normalize_required_capabilities(cls, values: list[str]) -> list[str]:
        """Reject blank or oversized names at the request validation boundary."""
        normalized = [value.strip() for value in values]
        if any(not value for value in normalized):
            raise ValueError("required capabilities must not contain blank names")
        if any(len(value) > MAX_NAME_LENGTH for value in normalized):
            raise ValueError(
                f"required capability names cannot exceed {MAX_NAME_LENGTH} characters"
            )
        return normalized

    def workflow_steps(self) -> list[WorkflowStep]:
        """Materialize the request's explicit or legacy-sequential dependencies."""
        steps = [WorkflowStep("step-1", "Select the model provider")]
        for number, requested_tool in enumerate(self.tools, start=2):
            if requested_tool.depends_on is None:
                dependencies = (f"step-{number - 1}",)
            else:
                dependencies = tuple(dict.fromkeys(("step-1", *requested_tool.depends_on)))
            steps.append(
                WorkflowStep(
                    f"step-{number}",
                    f"Execute registered tool: {requested_tool.name}",
                    dependencies,
                )
            )
        return steps

    @model_validator(mode="after")
    def validate_tool_dependency_graph(self) -> "AgentPlanRequest":
        """Reject unknown, cyclic, or otherwise invalid dependencies at ingress."""
        try:
            build_workflow_plan(self.workflow_steps())
        except (WorkflowPlanError, TypeError) as exc:
            raise ValueError("tool dependency graph is invalid") from exc
        return self

    def canonical_payload(self) -> dict[str, object]:
        """Serialize requests without implicit None fields to preserve old digests.

        New optional dependency declarations remain part of the digest when
        explicitly supplied, while legacy requests keep their pre-DAG identity.
        """
        payload = self.model_dump(mode="json", exclude_none=True)
        # required_capabilities was introduced after durable AgentPlanRequest
        # digests already existed. An empty default must retain the pre-field
        # serialization so old queued workflows can still be resumed.
        if not self.required_capabilities:
            payload.pop("required_capabilities", None)
        return payload


class AgentCore:
    """Build a policy-aware plan; this version does not invoke models or tools."""

    def __init__(
        self,
        model_router: ModelRouter,
        tool_registry: ToolRegistry,
        policy: PolicyEngine | None = None,
        *,
        permission_provider: Callable[[], frozenset[str]] | None = None,
    ) -> None:
        self.model_router = model_router
        self.tool_registry = tool_registry
        if policy is not None and policy is not tool_registry.policy:
            raise ValueError(
                "AgentCore policy must be the same instance used by ToolRegistry"
            )
        self.policy = tool_registry.policy
        self.permission_provider = permission_provider

    def _current_permissions(self) -> frozenset[str]:
        """Resolve owner grants at the policy boundary; lookup failures deny access."""
        if self.permission_provider is None:
            return frozenset()
        try:
            return frozenset(self.permission_provider())
        except Exception:  # noqa: BLE001 - permission lookup failures must fail closed
            return frozenset()

    @staticmethod
    def workflow_step_input_digest(
        request_step_number: int,
        requested_tool: AgentToolRequest,
    ) -> str:
        """Bind a durable step to its stable request identity and exact input payload."""
        if request_step_number < 2:
            raise ValueError("Tool request step number must be at least 2")
        definition = {
            "step_id": f"step-{request_step_number}",
            "tool_name": requested_tool.name,
            "payload": requested_tool.payload,
        }
        encoded = json.dumps(
            definition, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
        return hashlib.sha256(encoded).hexdigest()

    def ordered_tool_steps(
        self,
        request: AgentPlanRequest,
        plan: dict[str, object],
    ) -> list[tuple[int, int, AgentToolRequest]]:
        """Return tools in validated topological order with durable runtime positions.

        The first tuple field is the persisted execution-order position (provider
        selection is step 1). The second field is the original request step number.
        Keeping both values prevents recovery checkpoints from confusing request
        order with DAG execution order.
        """
        dependency_plan = plan.get("dependency_plan")
        if not isinstance(dependency_plan, dict):
            raise RuntimeError("Agent plan is missing its validated dependency graph")
        ordered_steps = dependency_plan.get("ordered_steps")
        if not isinstance(ordered_steps, list):
            raise RuntimeError("Agent dependency graph has no ordered steps")

        expected_step_ids = {
            "step-1",
            *(f"step-{number}" for number in range(2, len(request.tools) + 2)),
        }
        ordered_step_ids: list[str] = []
        graph_steps: list[WorkflowStep] = []
        for workflow_step in ordered_steps:
            if not isinstance(workflow_step, dict):
                raise RuntimeError("Agent dependency graph contains an invalid step")
            step_id = workflow_step.get("step_id")
            description = workflow_step.get("description")
            dependencies = workflow_step.get("depends_on")
            if (
                not isinstance(step_id, str)
                or not isinstance(description, str)
                or not isinstance(dependencies, list)
                or any(not isinstance(item, str) for item in dependencies)
            ):
                raise RuntimeError("Agent dependency graph contains invalid step metadata")
            ordered_step_ids.append(step_id)
            graph_steps.append(WorkflowStep(step_id, description, tuple(dependencies)))

        if (
            not ordered_step_ids
            or ordered_step_ids[0] != "step-1"
            or len(ordered_step_ids) != len(expected_step_ids)
            or len(set(ordered_step_ids)) != len(ordered_step_ids)
            or set(ordered_step_ids) != expected_step_ids
        ):
            raise RuntimeError(
                "Agent dependency graph must contain every expected step exactly once"
            )

        try:
            validated_ids = [
                item["step_id"]
                for item in build_workflow_plan(graph_steps).as_dict()["ordered_steps"]
            ]
        except (TypeError, ValueError) as exc:
            raise RuntimeError("Agent dependency graph is invalid") from exc
        if validated_ids != ordered_step_ids:
            raise RuntimeError(
                "Agent dependency graph is not in deterministic topological order"
            )

        ordered_tools: list[tuple[int, int, AgentToolRequest]] = []
        for runtime_step_number, step_id in enumerate(ordered_step_ids[1:], start=2):
            request_step_number = int(step_id.removeprefix("step-"))
            ordered_tools.append(
                (runtime_step_number, request_step_number, request.tools[request_step_number - 2])
            )
        return ordered_tools

    def execute(
        self,
        request: AgentPlanRequest,
        *,
        on_step: Callable[[int, str, str | None], None] | None = None,
        on_step_result: Callable[[int, str], None] | None = None,
        start_step: int = 2,
        should_cancel: Callable[[], bool] | None = None,
    ) -> dict[str, object]:
        """Execute only prevalidated, policy-allowed tools without model inference."""
        plan = self.plan(request)
        if not plan["execution_ready"]:
            return {
                "decision_mode": "controlled_tool_execution",
                "execution_started": False,
                "execution_completed": False,
                "model_inference_started": False,
                "tools_executed": False,
                "plan": plan,
                "results": [],
                "blocked": True,
            }

        results: list[dict[str, object]] = []
        if start_step < 2:
            raise ValueError("Tool execution start step must be at least 2")

        for runtime_step_number, _request_step_number, requested_tool in (
            self.ordered_tool_steps(request, plan)
        ):
            if runtime_step_number < start_step:
                continue
            if should_cancel is not None and should_cancel():
                return {
                    "decision_mode": "controlled_tool_execution",
                    "execution_started": bool(results),
                    "execution_completed": False,
                    "cancelled": True,
                    "model_inference_started": False,
                    "tools_executed": bool(results),
                    "plan": plan,
                    "results": results,
                    "error_code": "cancelled",
                    "blocked": False,
                }
            if on_step is not None:
                on_step(runtime_step_number, "running", None)
            try:
                result = self.tool_registry.invoke(
                    requested_tool.name,
                    requested_tool.payload,
                    granted_permissions=self._current_permissions(),
                )
            except ToolPolicyError as exc:
                error_code = (
                    "approval_required"
                    if exc.decision is PolicyDecision.REQUIRE_APPROVAL
                    else "policy_denied"
                )
                if on_step is not None:
                    on_step(runtime_step_number, "failed", error_code)
                return {
                    "decision_mode": "controlled_tool_execution",
                    "execution_started": True,
                    "execution_completed": False,
                    "model_inference_started": False,
                    "tools_executed": bool(results),
                    "plan": plan,
                    "results": results,
                    "failed_tool": requested_tool.name,
                    "error_code": error_code,
                    "blocked": True,
                }
            except (ToolExecutionError, ValueError, TypeError, KeyError, RuntimeError):
                if on_step is not None:
                    on_step(runtime_step_number, "failed", "tool_execution_failed")
                return {
                    "decision_mode": "controlled_tool_execution",
                    "execution_started": True,
                    "execution_completed": False,
                    "model_inference_started": False,
                    "tools_executed": bool(results),
                    "plan": plan,
                    "results": results,
                    "failed_tool": requested_tool.name,
                    "error_code": "tool_execution_failed",
                    "blocked": True,
                }
            results.append({"tool": requested_tool.name, "result": result})
            if on_step_result is not None:
                output_bytes = json.dumps(
                    result, ensure_ascii=False, sort_keys=True, separators=(",", ":")
                ).encode()
                on_step_result(runtime_step_number, hashlib.sha256(output_bytes).hexdigest())
            if on_step is not None:
                on_step(runtime_step_number, "succeeded", None)
            if should_cancel is not None and should_cancel():
                return {
                    "decision_mode": "controlled_tool_execution",
                    "execution_started": True,
                    "execution_completed": False,
                    "cancelled": True,
                    "model_inference_started": False,
                    "tools_executed": bool(results),
                    "plan": plan,
                    "results": results,
                    "error_code": "cancelled",
                    "blocked": False,
                }

        return {
            "decision_mode": "controlled_tool_execution",
            "execution_started": bool(results),
            "execution_completed": True,
            "model_inference_started": False,
            "tools_executed": bool(results),
            "plan": plan,
            "results": results,
            "blocked": False,
        }

    def plan(self, request: AgentPlanRequest) -> dict[str, object]:
        selection = self.model_router.select(
            ModelRequest(
                requires_text=request.requires_text,
                requires_vision=request.requires_vision,
                requires_audio=request.requires_audio,
                requires_tool_calling=request.requires_tool_calling,
                prefer_local=request.prefer_local,
            )
        )
        steps: list[dict[str, object]] = [
            {
                "step": 1,
                "kind": "provider_selection",
                "status": "selected",
                "provider": selection.provider,
                "model": selection.model,
                "local": selection.local,
            }
        ]

        for index, requested_tool in enumerate(request.tools, start=2):
            try:
                tool = self.tool_registry.get(requested_tool.name)
            except LookupError:
                steps.append(
                    {
                        "step": index,
                        "kind": "tool",
                        "name": requested_tool.name,
                        "status": "not_registered",
                        "decision": PolicyDecision.DENY.value,
                    }
                )
                continue

            try:
                tool.input_model.model_validate(requested_tool.payload)
            except ValidationError:
                steps.append(
                    {
                        "step": index,
                        "kind": "tool",
                        "name": requested_tool.name,
                        "status": "invalid_input",
                        "decision": PolicyDecision.DENY.value,
                    }
                )
                continue

            decision = self.tool_registry.evaluate_policy(
                tool.name,
                granted_permissions=self._current_permissions(),
            )
            status = {
                PolicyDecision.ALLOW: "ready",
                PolicyDecision.REQUIRE_APPROVAL: "approval_required",
                PolicyDecision.DENY: "blocked",
            }[decision.decision]
            steps.append(
                {
                    "step": index,
                    "kind": "tool",
                    "name": tool.name,
                    "status": status,
                    "decision": decision.decision.value,
                    "reason": decision.reason,
                }
            )

        capability_gaps = evaluate_capability_gaps(
            request.required_capabilities,
            self.tool_registry.catalog(),
        )
        executable = all(
            step["status"] == "ready"
            for step in steps
            if step["kind"] == "tool"
        ) and capability_gaps.complete
        dependency_plan = build_workflow_plan(request.workflow_steps()).as_dict()
        return {
            "goal_length": len(request.goal),
            "analysis_mode": "declarative_request",
            "selected_provider": selection.model_dump(),
            "steps": steps,
            "step_count": len(steps),
            "dependency_plan": dependency_plan,
            "capability_gaps": capability_gaps.as_dict(),
            "execution_ready": executable,
            "decision_mode": "plan_only",
            "model_inference_started": False,
            "tools_executed": False,
            "downloads_started": False,
        }
