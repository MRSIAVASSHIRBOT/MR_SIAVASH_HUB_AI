import pytest

from mrhub.agents.plan_revision import PlanRevisionInputError, revise_plan


def base_plan():
    return {"steps": [
        {"step_id": "a", "description": "Initial step", "dependencies": [], "status": "completed"},
        {"step_id": "b", "description": "Follow-up", "dependencies": ["a"], "status": "pending"},
    ]}


def test_revision_is_additive_review_only_and_preserves_completed_steps():
    revision = revise_plan(base_plan(), [{"criterion_id": "c1", "kind": "failed"}], revision=2)
    assert revision.added_step_ids == ("review-2-c1",)
    assert revision.preserved_completed_ids == ("a",)
    assert revision.requires_review and not revision.executable
    assert next(s for s in revision.steps if s.step_id == "a").status == "completed"


def test_unverified_gap_creates_evidence_review_step():
    revision = revise_plan({"steps": []}, [{"criterion_id": "c", "kind": "unverified"}], revision=1)
    assert "Collect and verify evidence" in revision.steps[0].description


@pytest.mark.parametrize("steps", [
    [{"step_id": "x", "description": "x", "dependencies": ["x"]}],
    [{"step_id": "x", "description": "x", "dependencies": ["y"]}],
    [
        {"step_id": "x", "description": "x", "dependencies": ["y"]},
        {"step_id": "y", "description": "y", "dependencies": ["x"]},
    ],
    [
        {"step_id": "x", "description": "x", "dependencies": []},
        {"step_id": "x", "description": "duplicate", "dependencies": []},
    ],
])
def test_invalid_dag_rejected(steps):
    with pytest.raises(PlanRevisionInputError):
        revise_plan({"steps": steps}, [{"criterion_id": "c", "kind": "failed"}], revision=1)


@pytest.mark.parametrize("revision,gaps", [
    (0, [{"criterion_id": "c", "kind": "failed"}]),
    (True, [{"criterion_id": "c", "kind": "failed"}]),
    (1, []),
    (1, [{"criterion_id": "c", "kind": "unexpected"}]),
])
def test_invalid_revision_or_gap_rejected(revision, gaps):
    with pytest.raises(PlanRevisionInputError):
        revise_plan({"steps": []}, gaps, revision=revision)


def test_duplicate_revision_step_is_not_added_twice():
    plan = {"steps": [{"step_id": "review-1-c", "description": "Existing", "dependencies": []}]}
    revision = revise_plan(plan, [{"criterion_id": "c", "kind": "failed"}], revision=1)
    assert revision.added_step_ids == ()
