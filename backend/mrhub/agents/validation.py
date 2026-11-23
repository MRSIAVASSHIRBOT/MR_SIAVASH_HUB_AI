"""Read-only consistency checks for AWI revision integration previews."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

MAX_STEPS = 100
MAX_TEXT = 500


@dataclass(frozen=True)
class ValidationReport:
    valid: bool
    findings: tuple[str, ...]
    checked_steps: int
    review_required: bool = True
    execution_permitted: bool = False


def validate_plan(plan: Mapping[str, object]) -> ValidationReport:
    """Validate bounded, untrusted plan data without raising on malformed fields."""
    if not isinstance(plan, Mapping):
        return ValidationReport(False, ("plan_not_mapping",), 0)
    raw = plan.get("steps")
    if not isinstance(raw, list) or len(raw) > MAX_STEPS:
        return ValidationReport(False, ("steps_not_bounded_list",), 0)

    findings: set[str] = set()
    steps: dict[str, dict[str, object]] = {}
    graph: dict[str, list[str]] = {}
    checked = len(raw)

    for item in raw:
        if not isinstance(item, dict):
            findings.add("step_not_mapping")
            continue
        sid, desc = item.get("step_id"), item.get("description")
        deps, status = item.get("dependencies", []), item.get("status", "pending")
        if not isinstance(sid, str) or not sid.strip() or len(sid) > MAX_TEXT:
            findings.add("invalid_step_id")
            continue
        if sid in steps:
            findings.add("duplicate_step_id")
            continue
        if not isinstance(desc, str) or not desc.strip() or len(desc) > MAX_TEXT:
            findings.add("invalid_description")
        if status not in ("pending", "completed", "blocked"):
            findings.add("invalid_status")

        valid_deps = isinstance(deps, list) and all(isinstance(d, str) for d in deps)
        if not valid_deps:
            findings.add("invalid_dependencies")
            normalized_deps: list[str] = []
        else:
            normalized_deps = list(deps)
            if len(normalized_deps) != len(set(normalized_deps)):
                findings.add("duplicate_dependency")
        steps[sid] = item
        graph[sid] = normalized_deps

    for sid, deps in graph.items():
        for dep in deps:
            if dep not in graph:
                findings.add("unknown_dependency")
            if dep == sid:
                findings.add("self_dependency")

    # Iterative DFS avoids recursion and traverses only normalized string edges.
    state: dict[str, int] = {}  # 0/unseen, 1/active, 2/finished
    for root in graph:
        if state.get(root, 0) == 2:
            continue
        stack: list[tuple[str, bool]] = [(root, False)]
        while stack:
            node, exiting = stack.pop()
            if exiting:
                state[node] = 2
                continue
            node_state = state.get(node, 0)
            if node_state == 2:
                continue
            if node_state == 1:
                findings.add("dependency_cycle")
                continue
            state[node] = 1
            stack.append((node, True))
            for dep in graph.get(node, []):
                if dep not in graph:
                    continue
                if state.get(dep, 0) == 1:
                    findings.add("dependency_cycle")
                elif state.get(dep, 0) == 0:
                    stack.append((dep, False))

    ordered = tuple(sorted(findings))
    return ValidationReport(not ordered, ordered, checked)
