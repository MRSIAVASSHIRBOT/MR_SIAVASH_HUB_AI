import pytest
from mrhub.agents.validation import validate_plan


def step(sid, deps=None, desc="task", status="pending"):
    return {"step_id": sid, "description": desc, "dependencies": deps or [], "status": status}


def test_valid_graph():
    r = validate_plan({"steps": [step("a"), step("b", ["a"])]})
    assert r.valid and r.execution_permitted is False and r.review_required


@pytest.mark.parametrize("steps, finding", [
    ([step("a", ["missing"])], "unknown_dependency"),
    ([step("a", ["a"])], "self_dependency"),
    ([step("a"), step("a")], "duplicate_step_id"),
    ([step("a", ["b"]), step("b", ["a"])], "dependency_cycle"),
    ([step("a", [["nested"]])], "invalid_dependencies"),
    ([step("a", ["x", "x"])], "duplicate_dependency"),
    ([step("a", desc="")], "invalid_description"),
    ([step("a", status="surprise")], "invalid_status"),
    ([None], "step_not_mapping"),
])
def test_invalid_graphs_are_reported(steps, finding):
    assert finding in validate_plan({"steps": steps}).findings


def test_unbounded_input_rejected():
    assert "steps_not_bounded_list" in validate_plan({"steps": [step(str(i)) for i in range(101)]}).findings


def test_non_mapping_plan_rejected():
    assert "plan_not_mapping" in validate_plan(None).findings


def test_cycle_reported_without_recursion():
    steps = [step("a", ["b"]), step("b", ["c"]), step("c", ["a"])]
    assert "dependency_cycle" in validate_plan({"steps": steps}).findings
