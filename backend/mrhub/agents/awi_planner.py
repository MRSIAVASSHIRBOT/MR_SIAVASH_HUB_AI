"""Bounded AWI planning: validate a dependency-aware plan without execution."""

import json
from collections.abc import Callable
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from mrhub.agents.work_order import WorkOrder
from mrhub.prompts.registry import DEFAULT_PROMPT_REGISTRY, PromptRender
from mrhub.providers.base import ProviderRequest
from mrhub.providers.router import ModelRequest, ModelRouter

MAX_PLAN_OUTPUT_CHARS = 16_000
MAX_PLAN_OUTPUT_TOKENS = 1_800
MAX_PLAN_STEP_ID_LENGTH = 40
MAX_PLAN_ITEM_TEXT_LENGTH = 300
MAX_PLAN_CAPABILITY_LENGTH = 80
_STEP_ID_PATTERN = r"^[a-z][a-z0-9_-]*$"

PlanStepIdentifier = Annotated[
    str, Field(min_length=1, max_length=MAX_PLAN_STEP_ID_LENGTH, pattern=_STEP_ID_PATTERN)
]
PlanDependencyIdentifier = Annotated[
    str, Field(min_length=1, max_length=MAX_PLAN_STEP_ID_LENGTH, pattern=_STEP_ID_PATTERN)
]
PlanCapabilityIdentifier = Annotated[
    str, Field(min_length=1, max_length=MAX_PLAN_CAPABILITY_LENGTH)
]
PlanCriterion = Annotated[
    str, Field(min_length=1, max_length=MAX_PLAN_ITEM_TEXT_LENGTH)
]


class PlanStep(BaseModel):
    """One declarative step. It describes intent and verification, not execution."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    step_id: PlanStepIdentifier
    description: str = Field(min_length=1, max_length=500)
    depends_on: list[PlanDependencyIdentifier] = Field(default_factory=list, max_length=12)
    required_capabilities: list[PlanCapabilityIdentifier] = Field(default_factory=list, max_length=20)
    verifies_criteria: list[PlanCriterion] = Field(min_length=1, max_length=12)
    verification: str = Field(min_length=1, max_length=500)

    @field_validator("description", "verification")
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("step text must not be blank")
        return normalized

    @field_validator("depends_on", "required_capabilities", "verifies_criteria")
    @classmethod
    def normalize_nonblank_items(cls, items: list[str]) -> list[str]:
        normalized = [item.strip() for item in items]
        if any(not item for item in normalized):
            raise ValueError("step list entries must not be blank")
        return normalized


class ExecutionPlan(BaseModel):
    """Validated plan with explicit evidence coverage and no executable payloads."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    steps: list[PlanStep] = Field(min_length=1, max_length=12)
    rationale: str = Field(min_length=1, max_length=1_000)

    @field_validator("rationale")
    @classmethod
    def normalize_rationale(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("rationale must not be blank")
        return normalized

    @model_validator(mode="after")
    def validate_graph(self) -> "ExecutionPlan":
        ids = [step.step_id for step in self.steps]
        if len(ids) != len(set(ids)):
            raise ValueError("step_id values must be unique")
        known = set(ids)
        graph: dict[str, list[str]] = {}
        for step in self.steps:
            if len(step.depends_on) != len(set(step.depends_on)):
                raise ValueError("step dependencies must be unique")
            if step.step_id in step.depends_on:
                raise ValueError("a step cannot depend on itself")
            if any(dep not in known for dep in step.depends_on):
                raise ValueError("step dependency references an unknown step")
            graph[step.step_id] = step.depends_on

        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(node: str) -> None:
            if node in visiting:
                raise ValueError("step dependency graph contains a cycle")
            if node in visited:
                return
            visiting.add(node)
            for dependency in graph[node]:
                visit(dependency)
            visiting.remove(node)
            visited.add(node)

        for node in ids:
            visit(node)
        return self


class PlanningError(ValueError):
    """Raised when the generated plan is malformed or incomplete."""


def generate_execution_plan(
    work_order: WorkOrder,
    model_router: ModelRouter,
    *,
    min_steps: int = 1,
    max_steps: int = 12,
    prompt_observer: Callable[[PromptRender], None] | None = None,
) -> ExecutionPlan:
    """Generate a bounded AWI plan and verify declared criteria/capability coverage."""
    if (
        isinstance(min_steps, bool)
        or isinstance(max_steps, bool)
        or not isinstance(min_steps, int)
        or not isinstance(max_steps, int)
        or not 1 <= min_steps <= max_steps <= 12
    ):
        raise ValueError("Plan step bounds must satisfy 1 <= min_steps <= max_steps <= 12")
    prompt_render = DEFAULT_PROMPT_REGISTRY.render(
        "awi.execution_plan",
        version=1,
        variables={
            "min_steps": str(min_steps),
            "max_steps": str(max_steps),
            "work_order_json": work_order.model_dump_json(),
        },
    )
    if prompt_observer is not None:
        prompt_observer(prompt_render)
    prompt = prompt_render.text
    response = model_router.generate(
        ModelRequest(requires_text=True),
        ProviderRequest(input_text=prompt, max_output_tokens=MAX_PLAN_OUTPUT_TOKENS),
    )
    raw = response.output_text
    if not isinstance(raw, str) or not raw.strip() or len(raw) > MAX_PLAN_OUTPUT_CHARS:
        raise PlanningError("Provider returned empty or oversized plan output")
    try:
        payload = json.loads(raw)
        plan = ExecutionPlan.model_validate(payload)
    except (json.JSONDecodeError, ValidationError, TypeError) as exc:
        raise PlanningError("Generated execution plan failed schema validation") from exc

    if not min_steps <= len(plan.steps) <= max_steps:
        raise PlanningError("Plan step count is outside the requested bounds")

    declared_criteria = set(work_order.acceptance_criteria)
    covered_criteria = {
        criterion for step in plan.steps for criterion in step.verifies_criteria
    }
    if covered_criteria != declared_criteria:
        raise PlanningError("Plan must cover every acceptance criterion and no unknown criteria")
    declared_capabilities = set(work_order.required_capabilities)
    planned_capabilities = {
        capability for step in plan.steps for capability in step.required_capabilities
    }
    if planned_capabilities != declared_capabilities:
        raise PlanningError("Plan must include every declared capability and no undeclared capabilities")
    return plan
