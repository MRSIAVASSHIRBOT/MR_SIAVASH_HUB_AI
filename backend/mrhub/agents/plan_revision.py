"""Bounded plan revision proposals from reviewed AWI gaps.

This module validates plan structure and produces additive review steps only.
It does not execute steps, invoke tools, or approve revisions.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

MAX_PLAN_STEPS = 100
MAX_TEXT_LENGTH = 500


class PlanRevisionInputError(ValueError):
    """Raised when the source plan is malformed or unsafe to revise structurally."""


@dataclass(frozen=True)
class PlanStep:
    step_id: str
    description: str
    dependencies: tuple[str, ...]
    status: str = "pending"


@dataclass(frozen=True)
class PlanRevision:
    revision: int
    steps: tuple[PlanStep, ...]
    added_step_ids: tuple[str, ...]
    preserved_completed_ids: tuple[str, ...]
    requires_review: bool = True
    executable: bool = False


def _validate_dag(steps: list[PlanStep]) -> None:
    ids = {step.step_id for step in steps}
    if len(ids) != len(steps):
        raise PlanRevisionInputError("Duplicate step identifiers")
    graph: dict[str, tuple[str, ...]] = {}
    for step in steps:
        if any(dep not in ids for dep in step.dependencies):
            raise PlanRevisionInputError("Unknown dependency")
        if step.step_id in step.dependencies:
            raise PlanRevisionInputError("Self-dependency is invalid")
        if len(set(step.dependencies)) != len(step.dependencies):
            raise PlanRevisionInputError("Duplicate dependency")
        graph[step.step_id] = step.dependencies

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> None:
        if node in visiting:
            raise PlanRevisionInputError("Dependency cycle detected")
        if node in visited:
            return
        visiting.add(node)
        for dependency in graph[node]:
            visit(dependency)
        visiting.remove(node)
        visited.add(node)

    for node in graph:
        visit(node)


def revise_plan(plan: Mapping[str, object], gaps: list[Mapping[str, object]], *, revision: int) -> PlanRevision:
    """Return a deterministic, additive revision proposal; never execute it."""
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
        raise PlanRevisionInputError("revision must be a positive integer")
    raw_steps = plan.get("steps")
    if not isinstance(raw_steps, list) or len(raw_steps) > MAX_PLAN_STEPS:
        raise PlanRevisionInputError("Plan steps must be a bounded list")
    if not isinstance(gaps, list) or not gaps or len(gaps) > MAX_PLAN_STEPS:
        raise PlanRevisionInputError("Gaps must be a non-empty bounded list")

    steps: list[PlanStep] = []
    for raw in raw_steps:
        if not isinstance(raw, dict):
            raise PlanRevisionInputError("Step entries must be mappings")
        step_id, description, deps, status = (
            raw.get("step_id"), raw.get("description"), raw.get("dependencies", []), raw.get("status", "pending")
        )
        if not isinstance(step_id, str) or not step_id.strip() or len(step_id) > MAX_TEXT_LENGTH:
            raise PlanRevisionInputError("Invalid step identifier")
        if not isinstance(description, str) or not description.strip() or len(description) > MAX_TEXT_LENGTH:
            raise PlanRevisionInputError("Invalid step description")
        if not isinstance(deps, list) or not all(isinstance(dep, str) for dep in deps):
            raise PlanRevisionInputError("Dependencies must be string lists")
        if status not in ("pending", "completed", "blocked"):
            raise PlanRevisionInputError("Unsupported step status")
        steps.append(PlanStep(step_id, description, tuple(deps), status))
    _validate_dag(steps)

    existing = {step.step_id for step in steps}
    completed = tuple(step.step_id for step in steps if step.status == "completed")
    added: list[str] = []
    for gap in gaps:
        if not isinstance(gap, Mapping):
            raise PlanRevisionInputError("Gap entries must be mappings")
        criterion_id, kind = gap.get("criterion_id"), gap.get("kind")
        if not isinstance(criterion_id, str) or not criterion_id.strip() or len(criterion_id) > MAX_TEXT_LENGTH:
            raise PlanRevisionInputError("Invalid gap criterion identifier")
        if kind not in ("failed", "unverified"):
            raise PlanRevisionInputError("Unsupported gap kind")
        new_id = f"review-{revision}-{criterion_id}"
        if new_id in existing:
            continue
        description = (
            f"Human review of evidence for criterion {criterion_id}."
            if kind == "failed"
            else f"Collect and verify evidence for criterion {criterion_id}."
        )
        steps.append(PlanStep(new_id, description, (), "pending"))
        existing.add(new_id)
        added.append(new_id)
        if len(steps) > MAX_PLAN_STEPS:
            raise PlanRevisionInputError("Revision exceeds supported step limit")

    _validate_dag(steps)
    return PlanRevision(revision, tuple(steps), tuple(added), completed)
