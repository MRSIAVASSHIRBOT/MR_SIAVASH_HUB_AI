"""Deterministic planning core connecting model routing, tools, and policy."""

import hashlib
import json
from collections.abc import Callable
from typing import Annotated
from uuid import UUID

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
from mrhub.tools.registry import (
    ToolExecutionError,
    ToolLifecycleObserver,
    ToolPolicyError,
    ToolRegistry,
)

WorkflowDependencyId = Annotated[
    str, Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9-]{0,63}$")
]


class AgentToolRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=80)
    payload: dict[str, object] = Field(default_factory=dict)
    # Explicit IDs survive harmless request reordering. Omitted IDs retain the
    # legacy position-derived identity for backward compatibility.
    step_id: WorkflowDependencyId | None = None
    # None preserves legacy sequential request order. An explicit list declares
    # dependencies on other request steps; provider selection is always implicit.
    depends_on: list[WorkflowDependencyId] | None = Field(default=None, max_length=5)
    # Optional owner-issued receipt, bound to this exact tool payload and definition.
    approval_id: UUID | None = None

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("tool name must not be blank")
        return normalized

    @field_validator("step_id")
    @classmethod
    def validate_step_id(cls, value: str | None) -> str | None:
        if value is not None and value != value.strip():
            raise ValueError("step_id cannot contain surrounding whitespace")
        return value

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
    # Optional one-time association with an encrypted, owner-scoped GPI/AWI plan.
    work_order_plan_id: UUID | None = None

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

    def tool_step_id(self, request_step_number: int, tool: AgentToolRequest) -> str:
        """Return the caller-stable identity or the legacy positional fallback."""
        return tool.step_id or f"step-{request_step_number}"

    def workflow_steps(self) -> list[WorkflowStep]:
        """Materialize stable IDs and explicit or legacy-sequential dependencies."""
        identities = [
            self.tool_step_id(number, tool)
            for number, tool in enumerate(self.tools, start=2)
        ]
        steps = [WorkflowStep("step-1", "Select the model provider")]
        for index, (requested_tool, step_id) in enumerate(
            zip(self.tools, identities, strict=True)
        ):
            if requested_tool.depends_on is None:
                dependency = "step-1" if index == 0 else identities[index - 1]
                dependencies = (dependency,)
            else:
                dependencies = tuple(
                    dict.fromkeys(("step-1", *requested_tool.depends_on))
                )
            steps.append(
                WorkflowStep(
                    step_id,
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
        # Order-independent request digests are safe only when every tool has
        # an explicit stable ID and an explicit dependency declaration.
        if self.tools and all(
            tool.step_id is not None and tool.depends_on is not None
            for tool in self.tools
        ):
            payload["tools"] = sorted(
                payload.get("tools", []),
                key=lambda item: item["step_id"],
            )
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
        approval_validator: Callable[[str, str, dict[str, object], frozenset[str]], bool] | None = None,
        approval_consumer: Callable[[str, str, dict[str, object], frozenset[str]], bool] | None = None,
    ) -> None:
        self.model_router = model_router
        self.tool_registry = tool_registry
        if policy is not None and policy is not tool_registry.policy:
            raise ValueError(
                "AgentCore policy must be the same instance used by ToolRegistry"
            )
        self.policy = tool_registry.policy
        self.permission_provider = permission_provider
        self.approval_validator = approval_validator
        self.approval_consumer = approval_consumer

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
        *,
        step_id: str | None = None,
    ) -> str:
        """Bind a durable step to its stable request identity and exact input payload."""
        if request_step_number < 2:
            raise ValueError("Tool request step number must be at least 2")
        definition = {
            "step_id": step_id or requested_tool.step_id or f"step-{request_step_number}",
            "tool_name": requested_tool.name,
            "payload": requested_tool.payload,
            "depends_on": (
                list(requested_tool.depends_on)
                if requested_tool.depends_on is not None
                else None
            ),
        }
        if requested_tool.approval_id is not None:
            definition["approval_id"] = str(requested_tool.approval_id)
        encoded = json.dumps(
            definition, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
        return hashlib.sha256(encoded).hexdigest()

    def ordered_tool_steps(
        self,
        request: AgentPlanRequest,
        plan: dict[str, object],
    ) -> list[tuple[int, int, AgentToolRequest]]:
        """Return tools in the request's exact validated DAG order.

        Runtime positions are durable checkpoint positions; request positions
        remain stable step identities. The planner output is checked against the
        graph derived from the original request so a valid but altered DAG cannot
        remove or rewrite a declared dependency.
        """
        dependency_plan = plan.get("dependency_plan")
        if not isinstance(dependency_plan, dict):
            raise TypeError("Agent plan is missing its validated dependency graph")

        try:
            expected_plan = build_workflow_plan(request.workflow_steps()).as_dict()
        except (TypeError, ValueError) as exc:
            raise RuntimeError("Agent request dependency graph is invalid") from exc

        if dependency_plan != expected_plan:
            raise RuntimeError(
                "Agent dependency graph does not match request dependency declarations"
            )

        ordered_steps = expected_plan["ordered_steps"]
        if not isinstance(ordered_steps, list) or not ordered_steps:
            raise RuntimeError("Agent dependency graph has no ordered steps")

        request_by_id = {
            request.tool_step_id(number, tool): (number, tool)
            for number, tool in enumerate(request.tools, start=2)
        }
        ordered_tools: list[tuple[int, int, AgentToolRequest]] = []
        for runtime_step_number, workflow_step in enumerate(ordered_steps[1:], start=2):
            stable_step_id = workflow_step["step_id"]
            request_item = request_by_id.get(stable_step_id)
            if request_item is None:
                raise RuntimeError("Validated dependency graph contains an unknown step identity")
            request_step_number, requested_tool = request_item
            ordered_tools.append(
                (runtime_step_number, request_step_number, requested_tool)
            )
        return ordered_tools

    def execute(
        self,
        request: AgentPlanRequest,
        *,
        on_step: Callable[[int, str, str | None], None] | None = None,
        on_step_result: Callable[[int, str], None] | None = None,
        start_step: int = 2,
        skip_step_ids: set[str] | frozenset[str] | None = None,
        should_cancel: Callable[[], bool] | None = None,
        on_tool_lifecycle: ToolLifecycleObserver | None = None,
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

        for runtime_step_number, request_step_number, requested_tool in (
            self.ordered_tool_steps(request, plan)
        ):
            stable_step_id = request.tool_step_id(request_step_number, requested_tool)
            if runtime_step_number < start_step or (
                skip_step_ids is not None and stable_step_id in skip_step_ids
            ):
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
                current_permissions = self._current_permissions()
                step_assessments = plan.get("steps", [])
                step_assessment = next(
                    (
                        item for item in step_assessments
                        if isinstance(item, dict)
                        and item.get("kind") == "tool"
                        and item.get("step") == request_step_number
                    ),
                    None,
                )
                if step_assessment is None:
                    raise ToolPolicyError(
                        PolicyDecision.DENY,
                        "The current plan has no matching tool assessment",
                    )

                tool = self.tool_registry.get(requested_tool.name)
                user_approved = False
                approval_required = step_assessment.get("approval_required") is True
                if approval_required:
                    # Avoid consuming a valid receipt after its owner grant has
                    # already been revoked. ToolRegistry performs the final
                    # server-side policy check again immediately before handler.
                    if not tool.required_permissions.issubset(current_permissions):
                        raise ToolPolicyError(
                            PolicyDecision.DENY,
                            "Required owner permissions are no longer active",
                        )
                    if (
                        step_assessment.get("approval_receipt_verified") is not True
                        or requested_tool.approval_id is None
                        or self.approval_consumer is None
                        or not self.approval_consumer(
                            str(requested_tool.approval_id),
                            requested_tool.name,
                            requested_tool.payload,
                            current_permissions,
                        )
                    ):
                        raise ToolPolicyError(
                            PolicyDecision.REQUIRE_APPROVAL,
                            "A valid owner approval receipt is required for this exact workflow step",
                        )
                    user_approved = True
                elif requested_tool.approval_id is not None:
                    raise ToolPolicyError(
                        PolicyDecision.DENY,
                        "Approval receipt does not match an action requiring approval",
                    )

                # Refresh owner grants after the potentially blocking receipt
                # lookup/consume and immediately before registry invocation.
                latest_permissions = self._current_permissions()
                if not tool.required_permissions.issubset(latest_permissions):
                    raise ToolPolicyError(
                        PolicyDecision.DENY,
                        "Required owner permissions are no longer active",
                    )
                current_permissions = latest_permissions
                result = self.tool_registry.invoke(
                    requested_tool.name,
                    requested_tool.payload,
                    granted_permissions=current_permissions,
                    user_approved=user_approved,
                    lifecycle_observer=on_tool_lifecycle,
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

            current_permissions = self._current_permissions()
            decision = self.tool_registry.evaluate_policy(
                tool.name,
                granted_permissions=current_permissions,
            )
            status = {
                PolicyDecision.ALLOW: "ready",
                PolicyDecision.REQUIRE_APPROVAL: "approval_required",
                PolicyDecision.DENY: "blocked",
            }[decision.decision]
            receipt_verified = False
            reason = decision.reason
            if (
                decision.decision is PolicyDecision.REQUIRE_APPROVAL
                and requested_tool.approval_id is not None
                and self.approval_validator is not None
            ):
                try:
                    receipt_verified = self.approval_validator(
                        str(requested_tool.approval_id),
                        requested_tool.name,
                        requested_tool.payload,
                        current_permissions,
                    )
                except Exception:  # noqa: BLE001 - invalid approval state must fail closed
                    receipt_verified = False
                if receipt_verified:
                    status = "approval_verified"
                    reason = "Owner approval receipt matches this exact tool input and current definition"
            steps.append(
                {
                    "step": index,
                    "kind": "tool",
                    "name": tool.name,
                    "status": status,
                    "decision": (
                        PolicyDecision.ALLOW.value
                        if receipt_verified
                        else decision.decision.value
                    ),
                    "approval_required": decision.decision is PolicyDecision.REQUIRE_APPROVAL,
                    "approval_receipt_verified": receipt_verified,
                    "reason": reason,
                }
            )

        # The catalog is bounded by the capability evaluator. Ordinary plans
        # without declared capability requirements must not fail merely because
        # the registered tool inventory grows beyond that assessment bound.
        catalog = (
            self.tool_registry.catalog()
            if request.required_capabilities
            else ()
        )
        capability_gaps = evaluate_capability_gaps(
            request.required_capabilities,
            catalog,
        )
        executable = all(
            step["status"] in {"ready", "approval_verified"}
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
