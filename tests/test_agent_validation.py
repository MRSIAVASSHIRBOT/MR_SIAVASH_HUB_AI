import pytest

from mrhub.agents.validation import validate_plan


def step(sid, deps=None):
    return {"step_id":sid,"description":"task","dependencies":deps or [],"status":"pending"}

def test_valid_graph():
    r=validate_plan({"steps":[step("a"),step("b",["a"])]})
    assert r.valid and r.execution_permitted is False and r.review_required

@pytest.mark.parametrize("steps, finding",[
    ([step("a",["missing"])],"unknown_dependency"),
    ([step("a",["a"])],"self_dependency"),
    ([step("a"),step("a")],"duplicate_step_id"),
    ([step("a",["b"]),step("b",["a"])],"dependency_cycle"),
])
def test_invalid_graphs(steps,finding):
    assert finding in validate_plan({"steps":steps}).findings

def test_unbounded_input_rejected():
    assert "steps_not_bounded_list" in validate_plan({"steps":[step(str(i)) for i in range(101)]}).findings
