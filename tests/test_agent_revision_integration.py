import pytest

from mrhub.agents.revision_integration import IntegrationInputError, preview_integration
from mrhub.agents.revision_review import compare_revisions, record_review


def plan(*steps):
    return {"steps": list(steps)}


def step(sid, desc="task", deps=None, status="pending"):
    return {"step_id": sid, "description": desc, "dependencies": deps or [], "status": status}


def approved(old, new, revision=1):
    diff = compare_revisions(old, new, revision=revision)
    return record_review(diff, reviewer="reviewer", approved=True)


def test_preview_accepts_approved_additive_revision():
    old, new = plan(step("a")), plan(step("a"), step("b", deps=["a"]))
    result = preview_integration(old, new, decision=approved(old, new))
    assert result.preserved_ids == ("a",)
    assert result.added_ids == ("b",)
    assert result.preview_only and result.review_required


def test_rejects_unapproved_decision():
    old, new = plan(step("a")), plan(step("b"))
    decision = record_review(compare_revisions(old, new, revision=1), reviewer="r", approved=False)
    with pytest.raises(IntegrationInputError):
        preview_integration(old, new, decision=decision)


def test_rejects_digest_mismatch():
    old, new = plan(step("a")), plan(step("a"), step("b"))
    other = plan(step("a"), step("c"))
    with pytest.raises(IntegrationInputError):
        preview_integration(old, new, decision=approved(old, other))


def test_rejects_modification_of_original_steps():
    old, new = plan(step("a")), plan(step("a", desc="modified"), step("b"))
    with pytest.raises(IntegrationInputError):
        preview_integration(old, new, decision=approved(old, new))


def test_rejects_removal_of_original_steps():
    old, new = plan(step("a")), plan()
    with pytest.raises(IntegrationInputError):
        preview_integration(old, new, decision=approved(old, new))


def test_rejects_invalid_dependency_graph():
    old, new = plan(step("a")), plan(step("a"), step("b", deps=["missing"]))
    with pytest.raises(IntegrationInputError):
        preview_integration(old, new, decision=approved(old, new))
