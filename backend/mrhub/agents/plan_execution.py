"""Strict bindings and integrity helpers for controlled AWI plan execution."""

from __future__ import annotations

import hashlib
import json
import re
from uuid import UUID

from pydantic import ValidationError

from mrhub.agents.awi_planner import ExecutionPlan, PlanStep
from mrhub.agents.core import AgentPlanRequest
from mrhub.tools.registry import ToolDefinition

PLAN_EXECUTION_FORMAT = "mrhub.awi-plan-execution.v1"
MAX_EXECUTABLE_STEPS = 5
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")


class PlanExecutionBindingError(ValueError):
    """Raised when a persisted plan cannot be mapped to a safe tool request."""


def canonical_digest(value: object) -> str:
    """Return SHA-256 over canonical, finite JSON data."""
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise PlanExecutionBindingError("Execution request must be finite JSON data") from exc
    return hashlib.sha256(encoded).hexdigest()


def tool_contract_digest(tool: ToolDefinition) -> str:
    """Fingerprint the server-owned tool schema and policy contract, never its handler."""
    return canonical_digest(
        {
            "name": tool.name,
            "input_schema": tool.input_model.model_json_schema(),
            "output_schema": tool.output_model.model_json_schema(),
            "risk_class": tool.risk_class.value,
            "required_permissions": sorted(tool.required_permissions),
            "external_side_effect": tool.external_side_effect,
        }
    )


def execution_request_digest(
    *,
    plan_id: str,
    plan_digest: str,
    bindings: list[dict[str, object]],
) -> str:
    """Digest the exact owner-submitted binding request for idempotent replay."""
    return canonical_digest(
        {
            "operation": PLAN_EXECUTION_FORMAT,
            "plan_id": plan_id,
            "plan_digest": plan_digest,
            "bindings": bindings,
        }
    )


def topological_plan_steps(plan: ExecutionPlan) -> list[PlanStep]:
    """Return a stable topological order, preserving original order among ready steps."""
    steps = list(plan.steps)
    known = {step.step_id for step in steps}
    if len(known) != len(steps):
        raise PlanExecutionBindingError("Plan step identifiers must be unique")
    completed: set[str] = set()
    ordered: list[PlanStep] = []

    while len(ordered) < len(steps):
        ready = [
            step
            for step in steps
            if step.step_id not in completed
            and all(dependency in completed for dependency in step.depends_on)
        ]
        if not ready:
            raise PlanExecutionBindingError("Plan dependency graph cannot be ordered")
        step = ready[0]
        if any(dependency not in known for dependency in step.depends_on):
            raise PlanExecutionBindingError("Plan contains an unknown dependency")
        completed.add(step.step_id)
        ordered.append(step)

    return ordered


def validate_plan_execution_payload(
    payload: object,
) -> tuple[AgentPlanRequest, dict[str, object]]:
    """Validate the encrypted plan-execution envelope used by the existing worker."""
    if not isinstance(payload, dict) or set(payload) != {
        "format",
        "request",
        "plan_binding",
    }:
        raise PlanExecutionBindingError("Plan execution envelope shape is invalid")
    if payload.get("format") != PLAN_EXECUTION_FORMAT:
        raise PlanExecutionBindingError("Unsupported plan execution envelope format")

    try:
        request = AgentPlanRequest.model_validate(payload["request"])
    except (ValidationError, TypeError, ValueError) as exc:
        raise PlanExecutionBindingError("Bound tool request failed schema validation") from exc

    binding = payload.get("plan_binding")
    if not isinstance(binding, dict) or set(binding) != {
        "plan_id",
        "plan_digest",
        "step_bindings",
    }:
        raise PlanExecutionBindingError("Plan binding metadata is invalid")

    plan_id = binding.get("plan_id")
    plan_digest = binding.get("plan_digest")
    entries = binding.get("step_bindings")
    try:
        canonical_plan_id = str(UUID(plan_id))
    except (TypeError, ValueError, AttributeError) as exc:
        raise PlanExecutionBindingError("Plan identifier is invalid") from exc
    if canonical_plan_id != plan_id:
        raise PlanExecutionBindingError("Plan identifier is not canonical")
    if not isinstance(plan_digest, str) or not _DIGEST_RE.fullmatch(plan_digest):
        raise PlanExecutionBindingError("Plan digest is invalid")
    if (
        not isinstance(entries, list)
        or not 1 <= len(entries) <= MAX_EXECUTABLE_STEPS
        or len(entries) != len(request.tools)
    ):
        raise PlanExecutionBindingError("Plan step binding count is invalid")

    seen_steps: set[str] = set()
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict) or set(entry) != {
            "step_id",
            "tool_name",
            "tool_contract_digest",
        }:
            raise PlanExecutionBindingError("Plan step binding entry is invalid")
        step_id = entry.get("step_id")
        tool_name = entry.get("tool_name")
        contract_digest = entry.get("tool_contract_digest")
        if not isinstance(step_id, str) or not step_id.strip() or len(step_id) > 40:
            raise PlanExecutionBindingError("Plan step identifier is invalid")
        if step_id in seen_steps:
            raise PlanExecutionBindingError("Plan step identifiers must be unique")
        seen_steps.add(step_id)
        if not isinstance(tool_name, str) or tool_name != request.tools[index].name:
            raise PlanExecutionBindingError("Plan step tool binding does not match the request")
        if not isinstance(contract_digest, str) or not _DIGEST_RE.fullmatch(contract_digest):
            raise PlanExecutionBindingError("Tool contract digest is invalid")

    return request, binding
