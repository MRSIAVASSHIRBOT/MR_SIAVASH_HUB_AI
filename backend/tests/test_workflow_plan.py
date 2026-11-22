import pytest

from mrhub.agents.workflow_plan import (
    WorkflowPlanError,
    WorkflowStep,
    build_workflow_plan,
)


def test_planner_returns_stable_topological_order_and_levels():
    plan = build_workflow_plan(
        [
            WorkflowStep("publish", "Publish", ("validate",)),
            WorkflowStep("collect", "Collect"),
            WorkflowStep("validate", "Validate", ("collect",)),
            WorkflowStep("notify", "Notify", ("publish",)),
        ]
    )

    assert [step.step_id for step in plan.ordered_steps] == [
        "collect", "validate", "publish", "notify"
    ]
    assert plan.dependency_levels == (
        ("collect",),
        ("validate",),
        ("publish",),
        ("notify",),
    )


def test_planner_preserves_input_order_for_independent_steps():
    plan = build_workflow_plan(
        [
            WorkflowStep("second", "Second"),
            WorkflowStep("first", "First"),
            WorkflowStep("third", "Third", ("second", "first")),
        ]
    )

    assert plan.dependency_levels == (("second", "first"), ("third",))


@pytest.mark.parametrize(
    "steps",
    [
        [],
        [WorkflowStep("a", "A"), WorkflowStep("a", "Duplicate")],
        [WorkflowStep("a", "A", ("missing",))],
        [WorkflowStep("a", "A", ("a",))],
        [
            WorkflowStep("a", "A", ("b",)),
            WorkflowStep("b", "B", ("a",)),
        ],
        [WorkflowStep(" ", "Invalid")],
        [WorkflowStep("a", " ")],
        [WorkflowStep("a", "A", ("b", "b")), WorkflowStep("b", "B")],
        [WorkflowStep("a", "A", (" ",))],
        [WorkflowStep("a", "A", (None,))],
        [WorkflowStep("a", "A", (["b"],))],
    ],
)
def test_planner_rejects_invalid_graphs(steps):
    with pytest.raises(WorkflowPlanError):
        build_workflow_plan(steps)


def test_planner_rejects_more_than_maximum_steps():
    steps = [WorkflowStep(f"step-{index}", "step") for index in range(101)]
    with pytest.raises(WorkflowPlanError, match="cannot contain more than"):
        build_workflow_plan(steps)


def test_plan_serialization_is_json_friendly():
    plan = build_workflow_plan(
        [WorkflowStep("a", "Collect"), WorkflowStep("b", "Check", ("a",))]
    )

    assert plan.as_dict() == {
        "ordered_steps": [
            {"step_id": "a", "description": "Collect", "depends_on": []},
            {"step_id": "b", "description": "Check", "depends_on": ["a"]},
        ],
        "dependency_levels": [["a"], ["b"]],
    }


def test_planner_stops_consuming_oversized_step_iterables():
    consumed = 0

    def step_stream():
        nonlocal consumed
        for index in range(1_000):
            consumed += 1
            yield WorkflowStep(f"step-{index}", "Step")

    with pytest.raises(WorkflowPlanError, match="cannot contain more than"):
        build_workflow_plan(step_stream())

    assert consumed == 101
