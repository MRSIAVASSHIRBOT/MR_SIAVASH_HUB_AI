"""Cross-module contract tests for the AWI proposal/review pipeline."""
from mrhub.agents.plan_revision import revise_plan
from mrhub.agents.revision_review import compare_revisions, record_review
from mrhub.agents.revision_integration import preview_integration
from mrhub.agents.validation import validate_plan
from mrhub.agents.review_export import export_review_summary


def plan(*steps):
    return {"steps": list(steps)}

def step(sid, desc="task", deps=None, status="pending"):
    return {"step_id":sid,"description":desc,"dependencies":deps or [],"status":status}


def test_full_review_pipeline_contract():
    original=plan(step("base",status="completed"))
    gaps=[{"criterion_id":"evidence-1","kind":"unverified"}]
    proposal=revise_plan(original,gaps,revision=2)
    candidate={"steps":[{"step_id":s.step_id,"description":s.description,
                         "dependencies":list(s.dependencies),"status":s.status}
                        for s in proposal.steps]}
    report=validate_plan(candidate)
    assert report.valid and report.execution_permitted is False
    diff=compare_revisions(original,candidate,revision=2)
    decision=record_review(diff,reviewer="test-reviewer",approved=True)
    preview=preview_integration(original,candidate,decision=decision)
    assert preview.preview_only and preview.review_required
    exported=export_review_summary({"revision":decision.revision,"digest":decision.digest,
                                    "approved":decision.approved,"findings":[]})
    assert exported["schema_version"]==1
    assert len(exported["sha256"])==64


def test_pipeline_rejects_tampered_candidate_after_review():
    original=plan(step("base",status="completed"))
    candidate=plan(step("base",status="completed"),step("new"))
    decision=record_review(compare_revisions(original,candidate,revision=1),
                           reviewer="reviewer",approved=True)
    tampered=plan(step("base",status="completed"),step("different"))
    try:
        preview_integration(original,tampered,decision=decision)
    except ValueError:
        pass
    else:
        raise AssertionError("tampered candidate should not match review digest")


def test_validation_report_never_authorizes_execution():
    report=validate_plan(plan(step("x")))
    assert report.valid
    assert report.execution_permitted is False
