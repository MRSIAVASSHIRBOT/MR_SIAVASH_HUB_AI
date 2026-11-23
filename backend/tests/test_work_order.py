import pytest
from pydantic import ValidationError

from mrhub.agents.work_order import WorkOrder
from mrhub.domain.tasks import RiskClass


def test_work_order_accepts_complete_structured_goal():
    order = WorkOrder(
        goal="Improve the task flow",
        intent="Reduce confusion and improve task completion",
        scope="Planning and status reporting only",
        assumptions=["The existing API remains stable"],
        constraints=["No production deploy"],
        dependencies=["Current task engine"],
        required_capabilities=["task planning"],
        acceptance_criteria=["The plan includes success criteria"],
        verification_steps=["Run contract tests"],
        risk_class=RiskClass.MODERATE,
    )
    assert order.goal == "Improve the task flow"
    assert order.acceptance_criteria == ["The plan includes success criteria"]


def test_work_order_requires_acceptance_verification_and_explicit_risk():
    with pytest.raises(ValidationError):
        WorkOrder(goal="Task", intent="Do the task")

    with pytest.raises(ValidationError):
        WorkOrder(
            goal="Task",
            intent="Do the task",
            acceptance_criteria=["Done means verified"],
            verification_steps=["Run tests"],
        )


@pytest.mark.parametrize("field", ["assumptions", "constraints", "dependencies", "required_capabilities", "acceptance_criteria", "verification_steps"])
def test_work_order_rejects_blank_list_items(field):
    payload = {
        "goal": "Task",
        "intent": "Intent",
        "acceptance_criteria": ["criterion"],
        "verification_steps": ["verify"],
    }
    payload[field] = [" "]
    with pytest.raises(ValidationError):
        WorkOrder(**payload)


def test_work_order_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        WorkOrder(
            goal="Task",
            intent="Intent",
            acceptance_criteria=["criterion"],
            verification_steps=["verify"],
            tool_permissions=["shell"],
        )


def test_work_order_capability_assessment_uses_shared_cgi_semantics():
    from mrhub.agents.work_order import assess_work_order_capabilities

    order = WorkOrder(
        goal="Review tool availability",
        intent="Report exact registered capability coverage",
        required_capabilities=["browser.search", "filesystem.read", "Browser.Search"],
        acceptance_criteria=["All capability gaps are reported"],
        verification_steps=["Compare exact registered names"],
        risk_class=RiskClass.LOW,
    )
    report = assess_work_order_capabilities(
        order,
        [
            {"name": "browser.search", "description": "web search"},
            {"name": "web_reader", "description": "filesystem read capability"},
        ],
    )

    assert report.required == ("browser.search", "filesystem.read")
    assert report.available == ("browser.search",)
    assert report.missing == ("filesystem.read",)
    assert report.complete is False
    assert report.as_dict() == {
        "required": ["browser.search", "filesystem.read"],
        "available": ["browser.search"],
        "missing": ["filesystem.read"],
        "complete": False,
    }


def test_work_order_keeps_its_narrower_capability_limit():
    payload = {
        "goal": "Task",
        "intent": "Intent",
        "required_capabilities": [f"tool.{index}" for index in range(21)],
        "acceptance_criteria": ["criterion"],
        "verification_steps": ["verify"],
        "risk_class": RiskClass.LOW,
    }
    with pytest.raises(ValidationError):
        WorkOrder.model_validate(payload)
