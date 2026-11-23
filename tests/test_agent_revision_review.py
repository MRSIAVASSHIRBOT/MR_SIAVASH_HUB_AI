import pytest

from mrhub.agents.revision_review import ReviewInputError, compare_revisions, record_review


def plan(*steps):
    return {"steps": list(steps)}


def step(sid, description="task", deps=None, status="pending"):
    return {"step_id": sid, "description": description, "dependencies": deps or [], "status": status}


def test_diff_categorizes_changes_and_digest_is_stable():
    old = plan(step("a"), step("b", deps=["a"]))
    new = plan(step("a", status="completed"), step("b", "updated", ["a"]), step("c"))
    diff = compare_revisions(old, new, revision=2)
    assert diff.added == ("c",)
    assert diff.changed == ("a", "b")
    assert diff.removed == ()
    assert compare_revisions(old, new, revision=2).digest == diff.digest


def test_review_record_bound_to_digest_and_no_execution_claim():
    diff = compare_revisions(plan(step("a")), plan(step("a"), step("b")), revision=1)
    decision = record_review(diff, reviewer="reviewer", approved=True, note="Reviewed")
    assert decision.digest == diff.digest
    assert decision.approved is True


@pytest.mark.parametrize("approved", ["yes", 1, None])
def test_requires_explicit_boolean_decision(approved):
    diff = compare_revisions(plan(step("a")), plan(step("b")), revision=1)
    with pytest.raises(ReviewInputError):
        record_review(diff, reviewer="reviewer", approved=approved)


@pytest.mark.parametrize("revision", [0, -1, True])
def test_revision_number_validated(revision):
    with pytest.raises(ReviewInputError):
        compare_revisions(plan(), plan(), revision=revision)


def test_duplicate_ids_rejected():
    with pytest.raises(ReviewInputError):
        compare_revisions(plan(step("a"), step("a")), plan(), revision=1)
