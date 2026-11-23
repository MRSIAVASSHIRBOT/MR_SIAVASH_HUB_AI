"""Deterministic, advisory decisions derived from a validated GPI/AWI plan."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from mrhub.agents.awi_planner import ExecutionPlan
from mrhub.agents.capability_gaps import CapabilityGapReport
from mrhub.agents.work_order import WorkOrder
from mrhub.agents.workflow_plan import WorkflowStep, build_workflow_plan
from mrhub.providers.router import ModelSelection


class ComplexityBand(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass(frozen=True)
class WorkOrderDecisionAssessment:
    """Explainable planning decisions; never an execution or authorization grant."""

    complexity_score: int
    complexity_band: ComplexityBand
    complexity_factors: dict[str, int]
    missing_information: tuple[str, ...]
    clarifying_questions: tuple[str, ...]
    research_required: bool
    research_questions: tuple[str, ...]
    matched_registered_tools: tuple[str, ...]
    missing_capabilities: tuple[str, ...]
    ordered_step_ids: tuple[str, ...]
    ordered_step_tool_mapping: tuple[dict[str, object], ...]
    model_selection: dict[str, object]

    def as_dict(self) -> dict[str, object]:
        clarification_required = bool(
            self.missing_information or self.clarifying_questions
        )
        tool_use_required = bool(
            self.matched_registered_tools or self.missing_capabilities
        )
        planning_readiness = (
            "needs_clarification"
            if clarification_required
            else "needs_research"
            if self.research_required
            else "ready_for_review"
        )
        return {
            "planning_readiness": planning_readiness,
            "tool_use_required": tool_use_required,
            "complexity": {
                "score": self.complexity_score,
                "band": self.complexity_band.value,
                "method": "deterministic_weighted_v1",
                "factors": dict(self.complexity_factors),
            },
            "clarification": {
                "required": clarification_required,
                "missing_information": list(self.missing_information),
                "questions": list(self.clarifying_questions),
                "resolve_before_execution": clarification_required,
            },
            "research": {
                "required": self.research_required,
                "questions": list(self.research_questions),
                "source": "validated_gpi_work_order",
                "research_started": False,
            },
            "tools": {
                "required": bool(self.matched_registered_tools or self.missing_capabilities),
                "matched_registered_tools": list(self.matched_registered_tools),
                "missing_capabilities": list(self.missing_capabilities),
                "authorization_checked": False,
                "execution_started": False,
            },
            "execution_order": {
                "ordered_step_ids": list(self.ordered_step_ids),
                "step_tool_mapping": [
                    dict(item) for item in self.ordered_step_tool_mapping
                ],
                "ordering": "stable_topological",
                "execution_started": False,
            },
            "model": {
                **self.model_selection,
                "selection_scope": "local_text_only_gpi_awi_planning",
            },
            "planning_only": True,
            "authorization_checked": False,
            "tools_executed": False,
        }


def _topological_order(plan: ExecutionPlan) -> tuple[str, ...]:
    """Use the canonical bounded workflow planner to order validated AWI steps."""
    workflow_steps = tuple(
        WorkflowStep(step.step_id, step.description, tuple(step.depends_on))
        for step in plan.steps
    )
    dependency_plan = build_workflow_plan(workflow_steps)
    return tuple(step.step_id for step in dependency_plan.ordered_steps)


def assess_work_order_decisions(
    work_order: WorkOrder,
    plan: ExecutionPlan,
    capability_report: CapabilityGapReport,
    model_selection: ModelSelection,
) -> WorkOrderDecisionAssessment:
    """Derive explainable complexity, clarification, research, tool and order hints.

    Every result is advisory. Exact capability-name matches are surfaced as
    candidates only; this function never checks grants, approves, or invokes a tool.
    """
    if not isinstance(work_order, WorkOrder):
        raise TypeError("work_order must be a validated WorkOrder")
    if not isinstance(plan, ExecutionPlan):
        raise TypeError("plan must be a validated ExecutionPlan")
    if not isinstance(capability_report, CapabilityGapReport):
        raise TypeError("capability_report must be a CapabilityGapReport")
    if not isinstance(model_selection, ModelSelection):
        raise TypeError("model_selection must be a ModelSelection")

    dependency_edges = sum(len(step.depends_on) for step in plan.steps)
    risk_points = {
        "low": 0,
        "moderate": 5,
        "high": 10,
        "prohibited": 100,
    }.get(work_order.risk_class.value, 100)
    factors = {
        "plan_steps": len(plan.steps) * 4,
        "dependency_edges": dependency_edges * 2,
        "required_capabilities": len(work_order.required_capabilities) * 2,
        "acceptance_criteria": len(work_order.acceptance_criteria) * 2,
        "verification_steps": len(work_order.verification_steps),
        "assumptions": len(work_order.assumptions),
        "missing_information": len(work_order.missing_information) * 4,
        "research_questions": len(work_order.research_questions) * 3,
        "risk_class": risk_points,
    }
    score = min(100, sum(factors.values()))
    band = (
        ComplexityBand.LOW
        if score <= 20
        else ComplexityBand.MEDIUM
        if score <= 45
        else ComplexityBand.HIGH
    )

    available = {name.casefold() for name in capability_report.available}
    missing = {name.casefold() for name in capability_report.missing}
    order = _topological_order(plan)
    step_by_id = {step.step_id: step for step in plan.steps}
    step_mapping: list[dict[str, object]] = []
    matched_tools: list[str] = []
    missing_tools: list[str] = []

    for step_id in order:
        step = step_by_id[step_id]
        candidates = [
            name for name in step.required_capabilities
            if name.casefold() in available
        ]
        gaps = [
            name for name in step.required_capabilities
            if name.casefold() in missing
        ]
        for name in candidates:
            if name not in matched_tools:
                matched_tools.append(name)
        for name in gaps:
            if name not in missing_tools:
                missing_tools.append(name)
        step_mapping.append({
            "step_id": step_id,
            "candidate_tools": candidates,
            "missing_capabilities": gaps,
        })

    # Preserve capability assessment order for capabilities not attached to an
    # individual step; the AWI planner should normally have assigned each one.
    for name in capability_report.available:
        if name not in matched_tools:
            matched_tools.append(name)
    for name in capability_report.missing:
        if name not in missing_tools:
            missing_tools.append(name)

    return WorkOrderDecisionAssessment(
        complexity_score=score,
        complexity_band=band,
        complexity_factors=factors,
        missing_information=tuple(work_order.missing_information),
        clarifying_questions=tuple(work_order.clarifying_questions),
        research_required=work_order.research_required,
        research_questions=tuple(work_order.research_questions),
        matched_registered_tools=tuple(matched_tools),
        missing_capabilities=tuple(missing_tools),
        ordered_step_ids=order,
        ordered_step_tool_mapping=tuple(step_mapping),
        model_selection=model_selection.model_dump(mode="json"),
    )
