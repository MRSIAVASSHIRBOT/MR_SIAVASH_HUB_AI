"""Read-only consistency checks for AWI revision integration previews."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

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

        valid_deps = (
            isinstance(deps, list)
            and len(deps) <= MAX_STEPS
            and all(
                isinstance(dep, str) and dep.strip() and len(dep) <= MAX_TEXT
                for dep in deps
            )
        )
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

    # Iterative three-color DFS: each active node has exactly one stack frame,
    # avoiding false cycle reports from queued-but-not-yet-entered siblings.
    state: dict[str, int] = {}  # 0/unseen, 1/active, 2/finished
    for root in graph:
        if state.get(root, 0) != 0:
            continue
        state[root] = 1
        stack: list[tuple[str, int]] = [(root, 0)]
        while stack:
            node, edge_index = stack[-1]
            edges = graph[node]
            if edge_index >= len(edges):
                stack.pop()
                state[node] = 2
                continue
            dep = edges[edge_index]
            stack[-1] = (node, edge_index + 1)
            if dep not in graph:
                continue
            dep_state = state.get(dep, 0)
            if dep_state == 1:
                findings.add("dependency_cycle")
            elif dep_state == 0:
                state[dep] = 1
                stack.append((dep, 0))

    ordered = tuple(sorted(findings))
    return ValidationReport(not ordered, ordered, checked)
