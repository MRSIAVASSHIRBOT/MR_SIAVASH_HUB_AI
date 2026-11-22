"""Deterministic, side-effect-free workflow dependency planning.

The planner validates a bounded DAG and returns a stable topological order.
It deliberately does not execute steps, grant tools, or make authorization decisions.
"""

from __future__ import annotations

from collections.abc import Iterable
from collections import deque
from dataclasses import dataclass


MAX_STEPS = 100
MAX_STEP_ID_LENGTH = 64
MAX_DESCRIPTION_LENGTH = 1_000


@dataclass(frozen=True)
class WorkflowStep:
    step_id: str
    description: str
    depends_on: tuple[str, ...] = ()


@dataclass(frozen=True)
class WorkflowPlan:
    ordered_steps: tuple[WorkflowStep, ...]
    dependency_levels: tuple[tuple[str, ...], ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "ordered_steps": [
                {
                    "step_id": step.step_id,
                    "description": step.description,
                    "depends_on": list(step.depends_on),
                }
                for step in self.ordered_steps
            ],
            "dependency_levels": [list(level) for level in self.dependency_levels],
        }


class WorkflowPlanError(ValueError):
    """Raised when a proposed workflow is not a valid bounded DAG."""


def build_workflow_plan(steps: Iterable[WorkflowStep]) -> WorkflowPlan:
    """Validate and topologically order steps, preserving input order for ties."""
    items = tuple(steps)
    if not items:
        raise WorkflowPlanError("A workflow must contain at least one step")
    if len(items) > MAX_STEPS:
        raise WorkflowPlanError(f"A workflow cannot contain more than {MAX_STEPS} steps")

    by_id: dict[str, WorkflowStep] = {}
    input_index: dict[str, int] = {}
    for index, step in enumerate(items):
        if not isinstance(step, WorkflowStep):
            raise TypeError("Every workflow item must be a WorkflowStep")
        if not isinstance(step.step_id, str):
            raise WorkflowPlanError("Step identifiers must be strings")
        step_id = step.step_id.strip()
        if not step_id or len(step_id) > MAX_STEP_ID_LENGTH:
            raise WorkflowPlanError(
                f"Step identifiers must contain 1 to {MAX_STEP_ID_LENGTH} characters"
            )
        if step_id != step.step_id:
            raise WorkflowPlanError("Step identifiers cannot contain surrounding whitespace")
        if step_id in by_id:
            raise WorkflowPlanError(f"Duplicate step identifier: {step_id}")
        if not isinstance(step.description, str) or not step.description.strip():
            raise WorkflowPlanError(f"Step {step_id} must have a non-blank description")
        if len(step.description) > MAX_DESCRIPTION_LENGTH:
            raise WorkflowPlanError(f"Step {step_id} description is too long")
        if not isinstance(step.depends_on, tuple):
            raise WorkflowPlanError(f"Dependencies for {step_id} must be a tuple")
        if len(set(step.depends_on)) != len(step.depends_on):
            raise WorkflowPlanError(f"Step {step_id} repeats a dependency")
        by_id[step_id] = step
        input_index[step_id] = index

    indegree = {step_id: 0 for step_id in by_id}
    dependents: dict[str, list[str]] = {step_id: [] for step_id in by_id}
    for step in items:
        for dependency in step.depends_on:
            if dependency not in by_id:
                raise WorkflowPlanError(
                    f"Step {step.step_id} depends on unknown step: {dependency}"
                )
            if dependency == step.step_id:
                raise WorkflowPlanError(f"Step {step.step_id} cannot depend on itself")
            indegree[step.step_id] += 1
            dependents[dependency].append(step.step_id)

    ready = deque(step_id for step_id in by_id if indegree[step_id] == 0)
    ordered: list[WorkflowStep] = []
    levels: list[tuple[str, ...]] = []
    remaining = dict(indegree)

    while ready:
        current_level = tuple(ready)
        ready.clear()
        levels.append(current_level)
        next_ready: list[str] = []
        for step_id in current_level:
            ordered.append(by_id[step_id])
            for dependent in dependents[step_id]:
                remaining[dependent] -= 1
                if remaining[dependent] == 0:
                    next_ready.append(dependent)
        next_ready.sort(key=input_index.__getitem__)
        ready.extend(next_ready)

    if len(ordered) != len(items):
        cyclic = tuple(step_id for step_id in by_id if remaining[step_id] > 0)
        raise WorkflowPlanError(f"Workflow contains a dependency cycle: {', '.join(cyclic)}")

    return WorkflowPlan(tuple(ordered), tuple(levels))
