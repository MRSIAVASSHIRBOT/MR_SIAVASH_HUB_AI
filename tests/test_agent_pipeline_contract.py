"""Cross-module contract tests for the AWI proposal and review pipeline."""
import pytest

from mrhub.agents.plan_revision import revise_plan
from mrhub.agents.review_export import export_review_summary
from mrhub.agents.revision_integration import (
    IntegrationInputError,
    preview_integration,
)
from mrhub.agents.revision_review import compare_revisions, record_review
from mrhub.agents.validation import validate_plan


def plan(*steps):
    return {"steps": list(steps)}


def step(step_id, description="task", dependencies=None, status="pending"):
    return {
        "step_id": step_id,
        "description": description,
        "dependencies": dependencies or [],
        "status": status,
    }


def test_full_proposal_review_validation_and_export_contract():
    original = plan(step("base", status="completed"))
    proposal = revise_plan(
        original,
        [{"criterion_id": "evidence-1", "kind": "unverified"}],
        revision=2,
    )
    candidate = {
        "steps": [
            {
                "step_id": item.step_id,
                "description": item.description,
                "dependencies": list(item.dependencies),
                "status": item.status,
            }
            for item in proposal.steps
        ]
    }

    validation = validate_plan(candidate)
    assert validation.valid
    assert validation.review_required
    assert validation.execution_permitted is False

    diff = compare_revisions(original, candidate, revision=2)
    decision = record_review(
        diff,
        reviewer="contract-test-reviewer",
        approved=True,
    )
    preview = preview_integration(original, candidate, decision=decision)

    assert preview.preview_only
    assert preview.review_required
    assert preview.preserved_ids == ("base",)
    assert len(preview.added_ids) == 1

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


def test_reviewed_candidate_cannot_be_tampered_before_integration():
    original = plan(step("base", status="completed"))
    candidate = plan(
        step("base", status="completed"),
        step("new-evidence-review"),
    )
    diff = compare_revisions(original, candidate, revision=1)
    decision = record_review(diff, reviewer="reviewer", approved=True)
    tampered = plan(
        step("base", status="completed"),
        step("different-step"),
    )

    with pytest.raises(IntegrationInputError):
        preview_integration(original, tampered, decision=decision)


def test_validated_plan_never_implies_execution_authorization():
    report = validate_plan(plan(step("review")))

    assert report.valid
    assert report.review_required
    assert report.execution_permitted is False
