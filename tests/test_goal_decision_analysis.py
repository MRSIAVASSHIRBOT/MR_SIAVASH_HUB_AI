from __future__ import annotations

import pytest

from mrhub.agents.goal_analysis import analyze_goal
from mrhub.agents.work_order import WorkOrder
from mrhub.domain.tasks import RiskClass


def test_general_information_question_does_not_request_clarification_or_tools() -> None:
    result = analyze_goal("What is an API?")

    assert result.complexity == "low"
    assert result.research_required is False
    assert result.tool_use_required is False
    assert result.clarification_recommended is False
    assert result.information_gaps == []
    assert result.model_requirements.modalities == ["text"]
    assert result.authorization_checked is False
    assert result.execution_started is False


def test_current_comparison_requires_research_signal() -> None:
    result = analyze_goal("Compare the latest Python release with the current stable release using official documentation.")

    assert result.research_required is True
    assert "freshness_or_external_evidence_signal" in result.reason_codes
    assert result.tool_use_required is False


def test_instructional_questions_with_action_verbs_do_not_request_tool_execution() -> None:
    examples = (
        "How do I delete a database?",
        "How to deploy a small application?",
        "Explain how to publish a website.",
        "مراحل حذف یک پایگاه داده چیست؟",
    )

    for goal in examples:
        result = analyze_goal(goal)
        assert result.tool_use_required is False
        assert result.model_requirements.tool_catalog_needed is False
        assert result.clarification_recommended is False
        assert "general_information_request" in result.reason_codes


def test_action_goal_selects_tool_catalog_but_not_authorization() -> None:
    result = analyze_goal("Build a small application and write unit tests.")

    assert result.tool_use_required is True
    assert result.model_requirements.tool_catalog_needed is True
    assert "action_or_capability_signal" in result.reason_codes
    assert result.authorization_checked is False
    assert result.execution_started is False


def test_visual_and_audio_inputs_are_reported_as_modalities() -> None:
    vision = analyze_goal("Analyze this screenshot and explain its layout.")
    audio = analyze_goal("Transcribe this voice recording.")

    assert "vision" in vision.model_requirements.modalities
    assert "audio" in audio.model_requirements.modalities
    assert vision.tool_use_required is False
    assert audio.tool_use_required is False


def test_content_generation_request_does_not_require_external_tools() -> None:
    result = analyze_goal("Write a short poem about the night sky.")

    assert result.tool_use_required is False
    assert result.model_requirements.tool_catalog_needed is False


def test_vague_goal_and_unresolved_assumptions_recommend_clarification() -> None:
    result = analyze_goal("Help me with my project.")

    assert result.clarification_recommended is True
    assert "requested_outcome" in result.information_gaps


def test_work_order_scope_and_capabilities_refine_decision_analysis() -> None:
    order = WorkOrder(
        goal="Build a small application",
        intent="Implement an application",
        scope="",
        assumptions=["The hosting target is unspecified."],
        constraints=[],
        dependencies=["connect to a database"],
        required_capabilities=["database.read"],
        acceptance_criteria=["Application starts successfully"],
        verification_steps=["Run the health test"],
        risk_class=RiskClass.LOW,
    )

    result = analyze_goal(order.goal, work_order=order)

    assert result.tool_use_required is True
    assert result.model_requirements.tool_catalog_needed is True
    assert result.clarification_recommended is True
    assert "target_scope" in result.information_gaps
    assert "unresolved_assumption_or_constraint" in result.information_gaps
    assert result.complexity_score > 5


def test_analysis_rejects_mismatched_work_order_goal() -> None:
    order = WorkOrder(
        goal="Build an application",
        intent="Implement an application",
        acceptance_criteria=["It starts"],
        verification_steps=["Run a test"],
        risk_class=RiskClass.LOW,
    )
    with pytest.raises(ValueError, match="must match"):
        analyze_goal("Build another application", work_order=order)


@pytest.mark.parametrize("goal", ["", "   ", "x" * 1_001])
def test_analysis_rejects_empty_or_oversized_goals(goal: str) -> None:
    with pytest.raises(ValueError, match="1 to 1000"):
        analyze_goal(goal)
