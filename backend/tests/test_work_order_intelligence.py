import pytest

from mrhub.agents.awi_planner import ExecutionPlan, PlanStep
from mrhub.agents.capability_gaps import CapabilityGapReport
from mrhub.agents.work_order import WorkOrder
from mrhub.agents.work_order_intelligence import (
    ComplexityLevel,
    ResearchDecision,
    ToolDecision,
    assess_work_order_intelligence,
)
from mrhub.domain.tasks import RiskClass


def make_work_order(
    *,
    goal="Prepare a software plan",
    scope="Planning and verification only",
    assumptions=None,
    dependencies=None,
    capabilities=None,
    estimated_complexity="moderate",
    missing_information=None,
    clarification_questions=None,
    research_required=False,
    research_questions=None,
):
    return WorkOrder(
        goal=goal,
        intent="Create an ordered, verifiable plan",
        scope=scope,
        assumptions=assumptions or [],
        dependencies=dependencies or [],
        required_capabilities=capabilities or [],
        estimated_complexity=estimated_complexity,
        missing_information=missing_information or [],
        clarification_questions=clarification_questions or [],
        research_required=research_required,
        research_questions=research_questions or [],
        acceptance_criteria=["The plan is verifiable"],
        verification_steps=["Run the focused test suite"],
        risk_class=RiskClass.LOW,
    )


def make_plan(step_count=2, *, chain=False, capabilities=None):
    steps = []
    for index in range(step_count):
        step_id = f"step{index + 1}"
        depends_on = [f"step{index}"] if chain and index else []
        steps.append(
            PlanStep(
                step_id=step_id,
                description=f"Complete step {index + 1}",
                depends_on=depends_on,
                required_capabilities=capabilities or [],
                verifies_criteria=["The plan is verifiable"],
                verification="Inspect the result and run tests",
            )
        )
    return ExecutionPlan(steps=steps, rationale="A bounded test plan")


def report(required=(), available=(), missing=()):
    return CapabilityGapReport(
        required=tuple(required),
        available=tuple(available),
        missing=tuple(missing),
    )


def test_simple_plan_is_low_complexity_and_has_no_automatic_action():
    result = assess_work_order_intelligence(
        make_work_order(),
        make_plan(),
        report(),
    ).as_dict()

    assert result["complexity"]["level"] == ComplexityLevel.LOW.value
    assert result["research"]["decision"] == ResearchDecision.NOT_INDICATED.value
    assert result["tools"]["decision"] == ToolDecision.NO_CAPABILITY_DECLARED.value
    assert result["execution_order"]["execution_started"] is False
    assert result["research"]["execution_started"] is False


def test_complexity_uses_bounded_step_dependency_and_capability_structure():
    order = make_work_order(
        assumptions=["A", "B", "C"],
        capabilities=["tool.one", "tool.two", "tool.three", "tool.four"],
    )
    result = assess_work_order_intelligence(
        order,
        make_plan(9, chain=True),
        report(
            required=order.required_capabilities,
            available=order.required_capabilities,
        ),
    )

    assert result.complexity is ComplexityLevel.HIGH
    assert result.complexity_score >= 6
    assert "deep_dependency_chain" in result.complexity_factors
    assert "many_required_capabilities" in result.complexity_factors
    assert "multiple_unverified_assumptions" in result.complexity_factors


def test_mid_sized_work_order_is_moderate_complexity():
    order = make_work_order(capabilities=["tool.one", "tool.two"])
    result = assess_work_order_intelligence(
        order,
        make_plan(5, chain=True),
        report(required=order.required_capabilities, available=order.required_capabilities),
    )
    assert result.complexity is ComplexityLevel.MODERATE


def test_missing_scope_assumptions_dependencies_and_capability_gaps_are_reported():
    order = make_work_order(
        scope="",
        assumptions=["Confirm supported API version"],
        dependencies=["Current database schema"],
        capabilities=["tool.available", "tool.missing"],
    )
    result = assess_work_order_intelligence(
        order,
        make_plan(capabilities=order.required_capabilities),
        report(
            required=order.required_capabilities,
            available=("tool.available",),
            missing=("tool.missing",),
        ),
    )

    assert result.information_gaps == (
        "scope_not_specified",
        "assumptions_require_confirmation",
        "declared_dependencies_require_validation",
        "required_capabilities_unavailable",
    )
    assert result.tool_decision is ToolDecision.BLOCKED_BY_CAPABILITY_GAPS


def test_all_registered_capabilities_still_do_not_imply_authorization():
    order = make_work_order(capabilities=["tool.alpha"])
    result = assess_work_order_intelligence(
        order,
        make_plan(capabilities=order.required_capabilities),
        report(required=("tool.alpha",), available=("tool.alpha",)),
    ).as_dict()

    assert (
        result["tools"]["decision"]
        == ToolDecision.CAPABILITIES_PRESENT_AUTHORIZATION_SEPARATE.value
    )
    assert result["tools"]["authorization_checked"] is False
    assert result["tools"]["tools_selected"] is False


@pytest.mark.parametrize(
    ("goal", "expected"),
    [
        ("Find the latest official API price today", ResearchDecision.REQUIRED),
        ("Research the official documentation", ResearchDecision.RECOMMENDED),
        ("Write a small local note-taking application", ResearchDecision.NOT_INDICATED),
    ],
)
def test_research_decision_is_explainable_and_does_not_start_research(goal, expected):
    result = assess_work_order_intelligence(
        make_work_order(goal=goal),
        make_plan(),
        report(),
    ).as_dict()

    assert result["research"]["decision"] == expected.value
    assert result["research"]["execution_started"] is False
    if expected is ResearchDecision.REQUIRED:
        assert result["declared_work_order_readiness"] == "ready_for_review"
        assert result["planning_readiness"] == "needs_research"


def test_plan_steps_are_returned_in_deterministic_topological_order():
    order = make_work_order()
    plan = ExecutionPlan(
        steps=[
            PlanStep(
                step_id="publish",
                description="Prepare publication",
                depends_on=["prepare"],
                verifies_criteria=["The plan is verifiable"],
                verification="Inspect the publication record",
            ),
            PlanStep(
                step_id="prepare",
                description="Prepare the content",
                verifies_criteria=["The plan is verifiable"],
                verification="Inspect the prepared content",
            ),
        ],
        rationale="Input order is not dependency order",
    )

    result = assess_work_order_intelligence(order, plan, report())

    assert result.ordered_step_ids == ("prepare", "publish")


def test_explicit_gpi_signals_drive_readiness_and_remain_advisory():
    order = make_work_order(
        estimated_complexity="high",
        missing_information=["The target runtime is not confirmed"],
        clarification_questions=["Which runtime should the plan target?"],
        research_required=True,
        research_questions=["Check the compatibility matrix from the vendor"],
    )

    payload = assess_work_order_intelligence(order, make_plan(), report()).as_dict()

    assert payload["complexity"]["model_estimate"] == "high"
    assert payload["planning_readiness"] == "needs_clarification"
    assert payload["information"]["status"] == "needs_clarification"
    assert payload["information"]["missing_information"] == [
        "The target runtime is not confirmed"
    ]
    assert payload["information"]["clarification_questions"] == [
        "Which runtime should the plan target?"
    ]
    assert "user_information_missing" in payload["information"]["gap_codes"]
    assert payload["research"]["decision"] == ResearchDecision.REQUIRED.value
    assert payload["research"]["questions"] == [
        "Check the compatibility matrix from the vendor"
    ]
    assert payload["research"]["execution_started"] is False
    assert payload["tools"]["authorization_checked"] is False
    assert payload["tools"]["tools_selected"] is False
    assert payload["planning_only"] is True
    assert payload["tools_executed"] is False


def test_rejects_cyclic_plan_instead_of_guessing_execution_order():
    with pytest.raises(ValueError):
        ExecutionPlan(
            steps=[
                PlanStep(
                    step_id="first",
                    description="First",
                    depends_on=["second"],
                    verifies_criteria=["The plan is verifiable"],
                    verification="Check first",
                ),
                PlanStep(
                    step_id="second",
                    description="Second",
                    depends_on=["first"],
                    verifies_criteria=["The plan is verifiable"],
                    verification="Check second",
                ),
            ],
            rationale="Cyclic input",
        )
