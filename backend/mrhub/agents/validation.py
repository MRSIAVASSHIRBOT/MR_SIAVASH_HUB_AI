"""Read-only consistency checks for AWI revision integration previews."""

from collections.abc import Mapping
from dataclasses import dataclass


MAX_STEPS = 100


@dataclass(frozen=True)
class ValidationReport:
    valid: bool
    findings: tuple[str, ...]
    checked_steps: int
    review_required: bool = True
    execution_permitted: bool = False


def validate_plan(plan: Mapping[str, object]) -> ValidationReport:
    raw = plan.get("steps")
    if not isinstance(raw, list) or len(raw) > MAX_STEPS:
        return ValidationReport(False, ("steps_not_bounded_list",), 0)
    findings: list[str] = []
    ids: list[str] = []
    steps: dict[str, dict] = {}
    for s in raw:
        if not isinstance(s, dict):
            findings.append("step_not_mapping")
            continue
        sid, desc, deps, status = s.get("step_id"), s.get("description"), s.get("dependencies", []), s.get("status", "pending")
        if not isinstance(sid, str) or not sid.strip() or len(sid)>500:
            findings.append("invalid_step_id"); continue
        if sid in steps: findings.append("duplicate_step_id")
        ids.append(sid)
        if not isinstance(desc, str) or not desc.strip() or len(desc)>500: findings.append("invalid_description")
        if not isinstance(deps, list) or not all(isinstance(d,str) for d in deps): findings.append("invalid_dependencies")
        elif len(deps)!=len(set(deps)): findings.append("duplicate_dependency")
        if status not in ("pending","completed","blocked"): findings.append("invalid_status")
        steps[sid]=s
    for sid,s in steps.items():
        deps=s.get("dependencies",[])
        if isinstance(deps,list):
            for d in deps:
                if d not in steps: findings.append("unknown_dependency")
                if d==sid: findings.append("self_dependency")
    graph={sid:s.get("dependencies",[]) for sid,s in steps.items()}
    visiting,visited=set(),set()
    def walk(n):
        if n in visiting: findings.append("dependency_cycle"); return
        if n in visited:return
        visiting.add(n)
        for d in graph.get(n,[]):
            if d in graph: walk(d)
        visiting.remove(n);visited.add(n)
    for n in graph:walk(n)
    findings=sorted(set(findings))
    return ValidationReport(not findings,tuple(findings),len(raw))
