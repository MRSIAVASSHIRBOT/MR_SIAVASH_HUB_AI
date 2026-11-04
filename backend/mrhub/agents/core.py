"""Deterministic planning core connecting model routing, tools, and policy."""

import hashlib
import json
from collections.abc import Callable

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from mrhub.providers.router import ModelRequest, ModelRouter
from mrhub.security.policy import PolicyDecision, PolicyEngine
from mrhub.tools.registry import ToolExecutionError, ToolPolicyError, ToolRegistry


class AgentToolRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=80)
    payload: dict[str, object] = Field(default_factory=dict)


class AgentPlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    goal: str = Field(min_length=1, max_length=1000)
    requires_text: bool = True
    requires_vision: bool = False
    requires_audio: bool = False
    requires_tool_calling: bool = False
    prefer_local: bool = False
    tools: list[AgentToolRequest] = Field(default_factory=list, max_length=5)


class AgentCore:
    """Build a policy-aware plan; this version does not invoke models or tools."""

    def __init__(
        self,
        model_router: ModelRouter,
        tool_registry: ToolRegistry,
        policy: PolicyEngine | None = None,
    ) -> None:
        self.model_router = model_router
        self.tool_registry = tool_registry
        if policy is not None and policy is not tool_registry.policy:
            raise ValueError(
                "AgentCore policy must be the same instance used by ToolRegistry"
            )
        self.policy = tool_registry.policy

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

        for step_number, requested_tool in enumerate(request.tools, start=2):
            if step_number < start_step:
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
                on_step(step_number, "running", None)
            try:
                result = self.tool_registry.invoke(
                    requested_tool.name, requested_tool.payload
                )
            except ToolPolicyError as exc:
                error_code = (
                    "approval_required"
                    if exc.decision is PolicyDecision.REQUIRE_APPROVAL
                    else "policy_denied"
                )
                if on_step is not None:
                    on_step(step_number, "failed", error_code)
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
                    on_step(step_number, "failed", "tool_execution_failed")
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
                on_step_result(step_number, hashlib.sha256(output_bytes).hexdigest())
            if on_step is not None:
                on_step(step_number, "succeeded", None)
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
            "execution_started": bool(request.tools),
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

            decision = self.tool_registry.evaluate_policy(tool.name)
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

        executable = all(
            step["status"] == "ready"
            for step in steps
            if step["kind"] == "tool"
        )
        return {
            "goal_length": len(request.goal),
            "analysis_mode": "declarative_request",
            "selected_provider": selection.model_dump(),
            "steps": steps,
            "step_count": len(steps),
            "execution_ready": executable,
            "decision_mode": "plan_only",
            "model_inference_started": False,
            "tools_executed": False,
            "downloads_started": False,
        }
