"""Tests for the advisory GPI WorkOrder decision contract."""

import pytest
from pydantic import ValidationError

from mrhub.agents.gpi import derive_server_risk_class
from mrhub.agents.work_order import WorkOrder
from mrhub.domain.tasks import RiskClass


def valid_work_order(**overrides: object) -> WorkOrder:
    values: dict[str, object] = {
        "goal": "Prepare a deployment review",
        "intent": "Review the deployment plan",
        "scope": "Local planning only",
        "assumptions": [],
        "constraints": ["Do not execute changes"],
        "dependencies": [],
        "required_capabilities": [],
        "acceptance_criteria": ["The plan has evidence"],
        "verification_steps": ["Review the evidence"],
        "risk_class": RiskClass.MODERATE,
    }
    values.update(overrides)
    return WorkOrder.model_validate(values)


def test_work_order_derives_readiness_and_tool_need_from_validated_fields() -> None:
    order = valid_work_order(required_capabilities=["research.search"])

    assert order.tool_use_required is True
    assert order.needs_clarification is False
    assert order.planning_readiness == "ready_for_review"


def test_missing_information_requires_a_concrete_clarification_question() -> None:
    with pytest.raises(ValidationError):
        valid_work_order(missing_information=["The deployment target is unknown"])

    order = valid_work_order(
        missing_information=["The deployment target is unknown"],
        clarification_questions=["Which environment should the plan target?"],
    )
    assert order.needs_clarification is True
    assert order.planning_readiness == "needs_clarification"


def test_research_requirement_must_include_research_questions() -> None:
    with pytest.raises(ValidationError):
        valid_work_order(research_required=True)

    order = valid_work_order(
        research_required=True,
        research_questions=["Which supported API version is current?"],
    )
    assert order.research_required is True
    assert order.planning_readiness == "needs_research"
    assert order.model_dump()["research_questions"] == [
        "Which supported API version is current?"
    ]


def test_research_questions_are_rejected_when_research_is_not_required() -> None:
    with pytest.raises(ValidationError):
        valid_work_order(
            research_required=False,
            research_questions=["Which API version is current?"],
        )


def test_server_risk_analysis_includes_clarification_and_research_text() -> None:
    assert derive_server_risk_class(
        "Review a project",
        {"clarification_questions": ["Does this publish to production?"]},
    ) is RiskClass.HIGH



def test_work_order_serialization_round_trips_without_computed_fields() -> None:
    order = valid_work_order(
        required_capabilities=["research.search"],
        research_required=True,
        research_questions=["Check the current official API version"],
    )

    payload = order.model_dump(mode="json")
    restored = WorkOrder.model_validate(payload)

    assert restored == order
    assert restored.tool_use_required is True
    assert restored.needs_clarification is False
    assert restored.planning_readiness == "needs_research"
    assert "needs_clarification" not in payload
    assert "tool_use_required" not in payload
    assert "planning_readiness" not in payload
