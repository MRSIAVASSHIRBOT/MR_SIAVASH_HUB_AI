from mrhub.agents.work_order_correction import (
    CorrectionAction,
    build_work_order_correction_proposal,
)
from mrhub.agents.work_order_evidence import (
    CriterionEvidenceResult,
    CriterionEvidenceStatus,
    WorkOrderDecision,
    WorkOrderEvidenceReport,
)


def _report() -> WorkOrderEvidenceReport:
    return WorkOrderEvidenceReport(
        work_order_id="wo_example",
        work_order_revision=1,
        work_order_digest="a" * 64,
        decision=WorkOrderDecision.REJECT,
        criteria=(
            CriterionEvidenceResult(
                criterion_id="ac_001",
                required=True,
                status=CriterionEvidenceStatus.FAILED,
                evidence_ids=("evidence_failed",),
                reason_codes=("verification_failed",),
            ),
            CriterionEvidenceResult(
                criterion_id="ac_002",
                required=True,
                status=CriterionEvidenceStatus.UNKNOWN,
                evidence_ids=(),
                reason_codes=("verification_unavailable",),
            ),
            CriterionEvidenceResult(
                criterion_id="ac_003",
                required=False,
                status=CriterionEvidenceStatus.FAILED,
                evidence_ids=("optional_failure",),
                reason_codes=("optional_failure",),
            ),
            CriterionEvidenceResult(
                criterion_id="ac_004",
                required=True,
                status=CriterionEvidenceStatus.STALE,
                evidence_ids=("stale_evidence",),
                reason_codes=("stale_work_order_reference",),
            ),
        ),
        report_digest="b" * 64,
    )


def test_failed_required_criterion_proposes_reviewed_correction_not_execution():
    proposal = build_work_order_correction_proposal(_report())
    body = proposal.as_dict()

    assert body["decision"] == "reject"
    assert body["items"][0]["criterion_id"] == "ac_001"
    assert body["items"][0]["action"] == CorrectionAction.PREPARE_REVIEWED_CORRECTION.value
    assert body["items"][1]["action"] == CorrectionAction.GATHER_OR_RECONCILE_EVIDENCE.value
    assert body["items"][2]["criterion_id"] == "ac_004"
    assert all(item["criterion_id"] != "ac_003" for item in body["items"])
    assert body["requires_owner_review"] is True
    assert body["plan_revision_created"] is False
    assert body["workflow_changed"] is False
    assert body["execution_started"] is False
    assert body["automatic_retry"] is False
    assert body["permissions_changed"] is False


def test_correction_proposal_digest_is_deterministic_and_evidence_bound():
    first = build_work_order_correction_proposal(_report())
    second = build_work_order_correction_proposal(_report())

    assert first.proposal_digest == second.proposal_digest
    assert first.as_dict() == second.as_dict()
    assert first.evidence_report_digest == "b" * 64
    assert first.work_order_digest == "a" * 64


def test_all_passed_required_criteria_produce_no_correction_items():
    report = WorkOrderEvidenceReport(
        work_order_id="wo_clean",
        work_order_revision=1,
        work_order_digest="c" * 64,
        decision=WorkOrderDecision.ACCEPT,
        criteria=(
            CriterionEvidenceResult(
                criterion_id="ac_001",
                required=True,
                status=CriterionEvidenceStatus.PASSED,
                evidence_ids=("verified",),
                reason_codes=("verified_success",),
            ),
        ),
        report_digest="d" * 64,
    )

    proposal = build_work_order_correction_proposal(report).as_dict()

    assert proposal["items"] == []
    assert proposal["decision"] == "accept"
    assert proposal["execution_started"] is False
