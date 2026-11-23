"""Explainable GPI assessment for complexity, information gaps and planning choices.

This module is deterministic and advisory. It does not perform research, select
or authorize tools, dispatch work, or change permissions.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from mrhub.agents.awi_planner import ExecutionPlan
from mrhub.agents.capability_gaps import CapabilityGapReport
from mrhub.agents.work_order import WorkOrder
from mrhub.agents.workflow_plan import WorkflowStep, build_workflow_plan


class ComplexityLevel(StrEnum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"


class ResearchDecision(StrEnum):
    REQUIRED = "required"
    RECOMMENDED = "recommended"
    NOT_INDICATED = "not_indicated"


class ToolDecision(StrEnum):
    NO_CAPABILITY_DECLARED = "no_capability_declared"
    BLOCKED_BY_CAPABILITY_GAPS = "blocked_by_capability_gaps"
    CAPABILITIES_PRESENT_AUTHORIZATION_SEPARATE = (
        "capabilities_present_authorization_separate"
    )


_FRESHNESS_SIGNALS = (
    "latest",
    "current",
    "today",
    "tonight",
    "this week",
    "this month",
    "recent",
    "up to date",
    "newest",
    "price",
    "pricing",
    "آخرین",
    "جدیدترین",
    "فعلی",
    "امروز",
    "امشب",
    "این هفته",
    "این ماه",
    "اخیر",
    "به روز",
    "قیمت",
)
_RESEARCH_SIGNALS = (
    "research",
    "investigate",
    "find sources",
    "cite sources",
    "documentation",
    "official docs",
    "benchmark",
    "survey",
    "literature",
    "compare sources",
    "تحقیق",
    "پژوهش",
    "منابع",
    "مستندات",
    "مستند رسمی",
    "بنچمارک",
    "مطالعات",
    "مقایسه منابع",
)
_SIGNAL_FIELDS = (
    "goal",
    "intent",
    "scope",
    "dependencies",
    "verification_steps",
    "acceptance_criteria",
    "missing_information",
    "clarification_questions",
    "research_questions",
)


@dataclass(frozen=True)
class WorkOrderIntelligenceAssessment:
    complexity: ComplexityLevel
    model_complexity_estimate: ComplexityLevel
    complexity_score: int
    complexity_factors: tuple[str, ...]
    information_gaps: tuple[str, ...]
    missing_information: tuple[str, ...]
    clarification_questions: tuple[str, ...]
    research_decision: ResearchDecision
    research_signals: tuple[str, ...]
    research_questions: tuple[str, ...]
    declared_work_order_readiness: str
    planning_readiness: str
    tool_decision: ToolDecision
    ordered_step_ids: tuple[str, ...]
    required_capabilities: tuple[str, ...]
    available_capabilities: tuple[str, ...]
    missing_capabilities: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "complexity": {
                "level": self.complexity.value,
                "structural_score": self.complexity_score,
                "model_estimate": self.model_complexity_estimate.value,
                "factors": list(self.complexity_factors),
                "method": "bounded_structural_heuristic_v1",
            },
            "information": {
                "status": (
                    "needs_clarification"
                    if self.missing_information or self.clarification_questions
                    else "review_required"
                    if self.information_gaps
                    else "no_detected_gaps"
                ),
                "gap_codes": list(self.information_gaps),
                "missing_information": list(self.missing_information),
                "clarification_questions": list(self.clarification_questions),
                "automatic_clarification_requested": False,
            },
            "research": {
                "decision": self.research_decision.value,
                "questions": list(self.research_questions),
                "signals": list(self.research_signals),
                "execution_started": False,
                "method": "explicit_work_order_plus_keyword_fallback_v1",
            },
            "tools": {
                "decision": self.tool_decision.value,
                "required": list(self.required_capabilities),
                "available": list(self.available_capabilities),
                "missing": list(self.missing_capabilities),
                "tools_selected": False,
                "authorization_checked": False,
            },
            "execution_order": {
                "step_ids": list(self.ordered_step_ids),
                "ordering": "validated_topological",
                "execution_started": False,
            },
            "declared_work_order_readiness": self.declared_work_order_readiness,
            "planning_readiness": self.planning_readiness,
            "planning_only": True,
            "authorization_checked": False,
            "tools_executed": False,
        }


def _planning_text(work_order: WorkOrder) -> str:
    values: list[str] = []
    for field in _SIGNAL_FIELDS:
        value = getattr(work_order, field)
        if isinstance(value, str):
            values.append(value)
        else:
            values.extend(item for item in value if isinstance(item, str))
    return " ".join(values).casefold().replace("ي", "ی").replace("ك", "ک")


def _matched_signals(text: str, signals: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(signal for signal in signals if signal.casefold() in text)


def assess_work_order_intelligence(
    work_order: WorkOrder,
    plan: ExecutionPlan,
    capability_report: CapabilityGapReport,
) -> WorkOrderIntelligenceAssessment:
    """Assess a validated work order without turning it into an executable command."""
    workflow_steps = tuple(
        WorkflowStep(step.step_id, step.description, tuple(step.depends_on))
        for step in plan.steps
    )
    dependency_plan = build_workflow_plan(workflow_steps)
    ordered_step_ids = tuple(step.step_id for step in dependency_plan.ordered_steps)

    step_count = len(plan.steps)
    dependency_count = sum(len(step.depends_on) for step in plan.steps)
    dependency_depth = len(dependency_plan.dependency_levels)
    capability_count = len(work_order.required_capabilities)
    assumption_count = len(work_order.assumptions)

    score = 0
    factors: list[str] = []
    if step_count >= 8:
        score += 2
        factors.append("many_plan_steps")
    elif step_count >= 4:
        score += 1
        factors.append("moderate_plan_step_count")

    if dependency_depth >= 5:
        score += 2
        factors.append("deep_dependency_chain")
    elif dependency_depth >= 3:
        score += 1
        factors.append("multi_level_dependencies")

    if capability_count >= 4:
        score += 2
        factors.append("many_required_capabilities")
    elif capability_count >= 2:
        score += 1
        factors.append("multiple_required_capabilities")

    if dependency_count >= 5:
        score += 1
        factors.append("many_dependency_edges")
    if assumption_count >= 3:
        score += 1
        factors.append("multiple_unverified_assumptions")

    if score >= 6:
        complexity = ComplexityLevel.HIGH
    elif score >= 3:
        complexity = ComplexityLevel.MODERATE
    else:
        complexity = ComplexityLevel.LOW

    information_gaps: list[str] = []
    if not work_order.scope.strip():
        information_gaps.append("scope_not_specified")
    if work_order.assumptions:
        information_gaps.append("assumptions_require_confirmation")
    if work_order.dependencies:
        information_gaps.append("declared_dependencies_require_validation")
    if work_order.missing_information:
        information_gaps.append("user_information_missing")
    if capability_report.missing:
        information_gaps.append("required_capabilities_unavailable")

    text = _planning_text(work_order)
    freshness = _matched_signals(text, _FRESHNESS_SIGNALS)
    research = _matched_signals(text, _RESEARCH_SIGNALS)
    if work_order.research_required:
        research_decision = ResearchDecision.REQUIRED
        research_signals = tuple(
            dict.fromkeys((*work_order.research_questions, *freshness, *research))
        )
    elif freshness:
        research_decision = ResearchDecision.REQUIRED
        research_signals = freshness + tuple(
            signal for signal in research if signal not in freshness
        )
    elif research:
        research_decision = ResearchDecision.RECOMMENDED
        research_signals = research
    else:
        research_decision = ResearchDecision.NOT_INDICATED
        research_signals = ()

    if not capability_report.required:
        tool_decision = ToolDecision.NO_CAPABILITY_DECLARED
    elif capability_report.missing:
        tool_decision = ToolDecision.BLOCKED_BY_CAPABILITY_GAPS
    else:
        tool_decision = ToolDecision.CAPABILITIES_PRESENT_AUTHORIZATION_SEPARATE

    planning_readiness = (
        "needs_clarification"
        if work_order.needs_clarification
        else "needs_research"
        if research_decision is ResearchDecision.REQUIRED
        else "ready_for_review"
    )

    return WorkOrderIntelligenceAssessment(
        complexity=complexity,
        model_complexity_estimate=ComplexityLevel(work_order.estimated_complexity),
        complexity_score=score,
        complexity_factors=tuple(factors),
        information_gaps=tuple(information_gaps),
        missing_information=tuple(work_order.missing_information),
        clarification_questions=tuple(work_order.clarification_questions),
        research_decision=research_decision,
        research_signals=research_signals,
        research_questions=tuple(work_order.research_questions),
        declared_work_order_readiness=work_order.planning_readiness,
        planning_readiness=planning_readiness,
        tool_decision=tool_decision,
        ordered_step_ids=ordered_step_ids,
        required_capabilities=capability_report.required,
        available_capabilities=capability_report.available,
        missing_capabilities=capability_report.missing,
    )
