"""Tests for explainable, non-executable GPI/AWI decision assessment."""

import pytest
from pydantic import ValidationError

from mrhub.agents.awi_planner import ExecutionPlan, PlanStep
from mrhub.agents.capability_gaps import CapabilityGapReport
from mrhub.agents.decision_assessment import (
    ComplexityBand,
    assess_work_order_decisions,
)
from mrhub.agents.work_order import WorkOrder
from mrhub.domain.tasks import RiskClass
from mrhub.providers.router import ModelSelection


def test_assessment_reports_gaps_research_and_dependency_order_without_execution():
    work_order = WorkOrder(
        goal="Prepare an evidence-based deployment plan",
        intent="Prepare a reviewed deployment plan",
        scope="Review only",
        assumptions=["The staging environment exists"],
        missing_information=["The target environment is not confirmed"],
        clarifying_questions=["Which environment should be reviewed?"],
        research_required=True,
        research_questions=["Check the currently supported deployment version"],
        required_capabilities=["tool.alpha", "tool.missing"],
        acceptance_criteria=["All deployment prerequisites are verified"],
        verification_steps=["Check the prerequisite evidence"],
        risk_class=RiskClass.MODERATE,
    )
    plan = ExecutionPlan(
        rationale="Inspect prerequisites before preparing the final plan",
        steps=[
            PlanStep(
                step_id="prepare",
                description="Prepare the reviewed plan",
                depends_on=["inspect"],
                required_capabilities=["tool.alpha"],
                verifies_criteria=["All deployment prerequisites are verified"],
                verification="Confirm the evidence is complete",
            ),
            PlanStep(
                step_id="inspect",
                description="Inspect available prerequisites",
                depends_on=[],
                required_capabilities=["tool.missing"],
                verifies_criteria=["All deployment prerequisites are verified"],
                verification="Record the prerequisite findings",
            ),
        ],
    )
    capability_report = CapabilityGapReport(
        required=("tool.alpha", "tool.missing"),
        available=("tool.alpha",),
        missing=("tool.missing",),
    )
    model_selection = ModelSelection(
        provider="ollama",
        model="local-text-model",
        local=True,
        rationale="Selected from registered available models by capability and priority",
    )

    result = assess_work_order_decisions(
        work_order,
        plan,
        capability_report,
        model_selection,
    ).as_dict()

    assert result["complexity"]["band"] in {
        ComplexityBand.MEDIUM.value,
        ComplexityBand.HIGH.value,
    }
    assert result["clarification"]["required"] is True
    assert result["clarification"]["resolve_before_execution"] is True
    assert result["planning_readiness"] == "needs_clarification"
    assert result["tool_use_required"] is True
    assert result["research"]["required"] is True
    assert result["research"]["research_started"] is False
    assert result["tools"]["matched_registered_tools"] == ["tool.alpha"]
    assert result["tools"]["missing_capabilities"] == ["tool.missing"]
    assert result["tools"]["authorization_checked"] is False
    assert result["execution_order"]["ordered_step_ids"] == ["inspect", "prepare"]
    assert result["execution_order"]["execution_started"] is False
    assert result["model"]["provider"] == "ollama"
    assert result["planning_only"] is True
    assert result["tools_executed"] is False


def test_complexity_is_deterministic_and_increases_with_dependency_work():
    basic = WorkOrder(
        goal="Summarize a short note",
        intent="Summarize the supplied note",
        acceptance_criteria=["The note is summarized"],
        verification_steps=["Check the summary against the note"],
        risk_class=RiskClass.LOW,
    )
    basic_plan = ExecutionPlan(
        rationale="One local transformation",
        steps=[
            PlanStep(
                step_id="summarize",
                description="Summarize the note",
                verifies_criteria=["The note is summarized"],
                verification="Compare summary to the source",
            )
        ],
    )
    report = CapabilityGapReport(required=(), available=(), missing=())
    model = ModelSelection(
        provider="ollama",
        model="local-text-model",
        local=True,
        rationale="Text capability match",
    )

    first = assess_work_order_decisions(basic, basic_plan, report, model).as_dict()
    second = assess_work_order_decisions(basic, basic_plan, report, model).as_dict()

    assert first == second
    assert first["complexity"]["score"] <= 20
    assert first["complexity"]["band"] == ComplexityBand.LOW.value
    assert first["planning_readiness"] == "ready_for_review"
    assert first["tool_use_required"] is False


def test_tool_capability_matches_are_candidates_not_authorization():
    work_order = WorkOrder(
        goal="Check a registered capability",
        intent="Check whether a capability is present",
        required_capabilities=["tool.alpha"],
        acceptance_criteria=["The capability is reported"],
        verification_steps=["Compare the exact capability name"],
        risk_class=RiskClass.LOW,
    )
    plan = ExecutionPlan(
        rationale="A single declarative step",
        steps=[
            PlanStep(
                step_id="check",
                description="Check the capability catalog",
                required_capabilities=["tool.alpha"],
                verifies_criteria=["The capability is reported"],
                verification="Inspect the catalog result",
            )
        ],
    )
    report = CapabilityGapReport(
        required=("tool.alpha",),
        available=("tool.alpha",),
        missing=(),
    )
    model = ModelSelection(
        provider="ollama",
        model="local-text-model",
        local=True,
        rationale="Text capability match",
    )

    result = assess_work_order_decisions(work_order, plan, report, model).as_dict()

    assert result["tools"]["matched_registered_tools"] == ["tool.alpha"]
    assert result["tools"]["authorization_checked"] is False
    assert result["tools"]["execution_started"] is False



def test_missing_information_requires_at_least_one_clarifying_question():
    with pytest.raises(ValidationError):
        WorkOrder(
            goal="Prepare a reviewed plan",
            intent="Prepare a reviewed plan",
            missing_information=["The target environment is unknown"],
            acceptance_criteria=["The plan is reviewed"],
            verification_steps=["Check the review result"],
            risk_class=RiskClass.LOW,
        )


def test_research_required_sets_planning_readiness_without_starting_research():
    work_order = WorkOrder(
        goal="Check the current supported API version",
        intent="Identify the supported API version",
        research_required=True,
        research_questions=["Which API version is currently supported?"],
        acceptance_criteria=["The version is supported"],
        verification_steps=["Check the official source"],
        risk_class=RiskClass.LOW,
    )
    plan = ExecutionPlan(
        rationale="Research is a planning requirement only",
        steps=[
            PlanStep(
                step_id="verify",
                description="Verify the current API version",
                verifies_criteria=["The version is supported"],
                verification="Compare with the official source",
            )
        ],
    )
    report = CapabilityGapReport(required=(), available=(), missing=())
    model = ModelSelection(
        provider="ollama",
        model="local-text-model",
        local=True,
        rationale="Local text-only planning",
    )

    result = assess_work_order_decisions(work_order, plan, report, model).as_dict()

    assert result["planning_readiness"] == "needs_research"
    assert result["research"]["required"] is True
    assert result["research"]["research_started"] is False
