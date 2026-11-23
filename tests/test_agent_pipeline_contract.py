"""Cross-module contract tests for the AWI proposal/review pipeline."""
import pytest

from mrhub.agents.plan_revision import revise_plan
from mrhub.agents.review_export import export_review_summary
from mrhub.agents.revision_integration import preview_integration
from mrhub.agents.revision_review import compare_revisions, record_review
from mrhub.agents.validation import validate_plan


def make_plan(*steps):
    return {"steps": list(steps)}


def make_step(step_id, description="task", dependencies=None, status="pending"):
    return {
        "step_id": step_id,
        "description": description,
        "dependencies": dependencies or [],
        "status": status,
    }


def test_full_review_pipeline_contract_remains_proposal_only():
    original = make_plan(make_step("base", status="completed"))
    gaps = [{"criterion_id": "evidence-1", "kind": "unverified"}]

    proposal = revise_plan(original, gaps, revision=2)
    candidate = {
        "steps": [
            {
                "step_id": step.step_id,
                "description": step.description,
                "dependencies": list(step.dependencies),
                "status": step.status,
            }
            for step in proposal.steps
        ]
    }

    report = validate_plan(candidate)
    assert report.valid
    assert report.execution_permitted is False

    diff = compare_revisions(original, candidate, revision=2)
    decision = record_review(diff, reviewer="test-reviewer", approved=True)
    preview = preview_integration(original, candidate, decision=decision)

    assert preview.preview_only
    assert preview.review_required

    exported = export_review_summary(
        {
            "revision": decision.revision,
            "digest": decision.digest,
            "approved": decision.approved,
            "findings": [],
        }
    )
    assert exported["schema_version"] == 1
    assert len(exported["sha256"]) == 64


def test_pipeline_rejects_candidate_tampered_after_review():
    original = make_plan(make_step("base", status="completed"))
    candidate = make_plan(
        make_step("base", status="completed"),
        make_step("new"),
    )
    decision = record_review(
        compare_revisions(original, candidate, revision=1),
        reviewer="reviewer",
        approved=True,
    )
    tampered = make_plan(
        make_step("base", status="completed"),
        make_step("different"),
    )

    with pytest.raises(ValueError):
        preview_integration(original, tampered, decision=decision)


def test_validation_never_grants_execution_permission():
    report = validate_plan(make_plan(make_step("x")))

    assert report.valid
    assert report.review_required
    assert report.execution_permitted is False
