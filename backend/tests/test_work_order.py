from pydantic import ValidationError
import pytest

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


def test_work_order_requires_acceptance_and_verification():
    with pytest.raises(ValidationError):
        WorkOrder(goal="Task", intent="Do the task")


@pytest.mark.parametrize("field", ["assumptions", "constraints", "dependencies", "required_capabilities", "acceptance_criteria", "verification_steps"])
def test_work_order_rejects_blank_list_items(field):
    with pytest.raises(ValidationError):
        WorkOrder(
            goal="Task",
            intent="Intent",
            acceptance_criteria=["criterion"],
            verification_steps=["verify"],
            **{field: [" "]},
        )


def test_work_order_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        WorkOrder(
            goal="Task",
            intent="Intent",
            acceptance_criteria=["criterion"],
            verification_steps=["verify"],
            tool_permissions=["shell"],
        )
