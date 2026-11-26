from __future__ import annotations

from collections.abc import Iterable

import pytest

from mrhub.agents.work_order_evidence import (
    CriterionEvidenceStatus,
    EvidenceInputError,
    EvidenceReference,
    EvidenceVerification,
    EvidenceVerifierRegistry,
    VerifierStatus,
    WorkOrderCriterion,
    WorkOrderDecision,
    WorkOrderSnapshot,
    evaluate_work_order_evidence,
)

WORK_ORDER_DIGEST = "a" * 64
EVIDENCE_DIGEST = "b" * 64


def snapshot(*, revision: int = 1) -> WorkOrderSnapshot:
    return WorkOrderSnapshot(
        work_order_id="workorder-123",
        revision=revision,
        digest=WORK_ORDER_DIGEST,
        criteria=(WorkOrderCriterion("ac_001"),),
    )


def reference(
    evidence_id: str = "evidence-001",
    *,
    work_order_digest: str = WORK_ORDER_DIGEST,
    work_order_revision: int = 1,
    evidence_digest: str = EVIDENCE_DIGEST,
    verifier_id: str = "github.status",
) -> EvidenceReference:
    return EvidenceReference(
        evidence_id=evidence_id,
        criterion_id="ac_001",
        source_type="github.check",
        source_ref="actions/runs/123",
        evidence_digest=evidence_digest,
        work_order_digest=work_order_digest,
        work_order_revision=work_order_revision,
        observed_at="2026-11-27T00:00:00+00:00",
        verifier_id=verifier_id,
    )


def registry_for(status: VerifierStatus = VerifierStatus.PASSED) -> EvidenceVerifierRegistry:
    registry = EvidenceVerifierRegistry()
    registry.register(
        source_type="github.check",
        verifier_id="github.status",
        verifier=lambda item, criterion: EvidenceVerification(
            status=status,
            evidence_digest=(
                item.evidence_digest if status is not VerifierStatus.UNKNOWN else None
            ),
            reason_code=f"test_{status.value}",
        ),
    )
    return registry


def test_trusted_current_evidence_accepts_required_criterion_without_leaking_source():
    report = evaluate_work_order_evidence(
        snapshot(),
        [reference()],
        registry_for(),
    )

    assert report.decision is WorkOrderDecision.ACCEPT
    assert report.criteria[0].status is CriterionEvidenceStatus.PASSED
    assert report.as_dict()["read_only"] is True
    assert report.as_dict()["execution_started"] is False
    assert report.as_dict()["permissions_changed"] is False
    assert "actions/runs/123" not in str(report.as_dict())


def test_missing_required_evidence_requires_review():
    report = evaluate_work_order_evidence(snapshot(), [], registry_for())

    assert report.decision is WorkOrderDecision.REVIEW_REQUIRED
    assert report.criteria[0].status is CriterionEvidenceStatus.UNKNOWN


def test_unregistered_verifier_is_unknown_not_accepted():
    report = evaluate_work_order_evidence(
        snapshot(),
        [reference(verifier_id="unregistered.check")],
        registry_for(),
    )

    assert report.decision is WorkOrderDecision.REVIEW_REQUIRED
    assert report.criteria[0].status is CriterionEvidenceStatus.UNKNOWN
    assert "unregistered_verifier" in report.criteria[0].reason_codes


def test_failed_required_evidence_rejects_work_order():
    report = evaluate_work_order_evidence(
        snapshot(),
        [reference()],
        registry_for(VerifierStatus.FAILED),
    )

    assert report.decision is WorkOrderDecision.REJECT
    assert report.criteria[0].status is CriterionEvidenceStatus.FAILED


def test_stale_work_order_revision_never_passes():
    report = evaluate_work_order_evidence(
        snapshot(revision=2),
        [reference(work_order_revision=1)],
        registry_for(),
    )

    assert report.decision is WorkOrderDecision.REVIEW_REQUIRED
    assert report.criteria[0].status is CriterionEvidenceStatus.STALE
    assert "stale_work_order_reference" in report.criteria[0].reason_codes


def test_digest_mismatch_from_verifier_is_unknown_not_passed():
    registry = EvidenceVerifierRegistry()
    registry.register(
        source_type="github.check",
        verifier_id="github.status",
        verifier=lambda item, criterion: EvidenceVerification(
            VerifierStatus.PASSED,
            evidence_digest="c" * 64,
            reason_code="verification_passed",
        ),
    )

    report = evaluate_work_order_evidence(snapshot(), [reference()], registry)

    assert report.decision is WorkOrderDecision.REVIEW_REQUIRED
    assert report.criteria[0].status is CriterionEvidenceStatus.UNKNOWN
    assert "evidence_digest_mismatch" in report.criteria[0].reason_codes


def test_conflicting_verifier_results_require_review():
    registry = EvidenceVerifierRegistry()
    registry.register(
        source_type="github.check",
        verifier_id="github.status",
        verifier=lambda item, criterion: EvidenceVerification(
            VerifierStatus.PASSED
            if item.evidence_id == "evidence-pass"
            else VerifierStatus.FAILED,
            evidence_digest=item.evidence_digest,
            reason_code="verification_result",
        ),
    )

    report = evaluate_work_order_evidence(
        snapshot(),
        [reference("evidence-pass"), reference("evidence-fail")],
        registry,
    )

    assert report.decision is WorkOrderDecision.REVIEW_REQUIRED
    assert report.criteria[0].status is CriterionEvidenceStatus.CONFLICTING


def test_verifier_exception_fails_closed_as_unknown():
    registry = EvidenceVerifierRegistry()

    def broken_verifier(item, criterion):
        raise RuntimeError("must not escape into a public report")

    registry.register(
        source_type="github.check",
        verifier_id="github.status",
        verifier=broken_verifier,
    )
    report = evaluate_work_order_evidence(snapshot(), [reference()], registry)

    assert report.decision is WorkOrderDecision.REVIEW_REQUIRED
    assert report.criteria[0].reason_codes == ("verifier_error",)


def test_invalid_verifier_output_fails_closed():
    registry = EvidenceVerifierRegistry()
    registry.register(
        source_type="github.check",
        verifier_id="github.status",
        verifier=lambda item, criterion: {"status": "passed"},
    )

    report = evaluate_work_order_evidence(snapshot(), [reference()], registry)

    assert report.decision is WorkOrderDecision.REVIEW_REQUIRED
    assert "invalid_verifier_response" in report.criteria[0].reason_codes


def test_unknown_verification_cannot_claim_a_digest():
    registry = EvidenceVerifierRegistry()
    registry.register(
        source_type="github.check",
        verifier_id="github.status",
        verifier=lambda item, criterion: EvidenceVerification(
            VerifierStatus.UNKNOWN,
            evidence_digest=item.evidence_digest,
            reason_code="verification_unavailable",
        ),
    )

    report = evaluate_work_order_evidence(snapshot(), [reference()], registry)

    assert report.decision is WorkOrderDecision.REVIEW_REQUIRED
    assert "unknown_result_claims_digest" in report.criteria[0].reason_codes


def test_duplicate_evidence_ids_are_rejected():
    with pytest.raises(EvidenceInputError, match="unique"):
        evaluate_work_order_evidence(
            snapshot(),
            [reference("duplicate"), reference("duplicate")],
            registry_for(),
        )


def test_duplicate_verifier_registration_is_rejected():
    registry = registry_for()
    with pytest.raises(EvidenceInputError, match="duplicated"):
        registry.register(
            source_type="github.check",
            verifier_id="github.status",
            verifier=lambda item, criterion: EvidenceVerification(
                VerifierStatus.PASSED,
                evidence_digest=item.evidence_digest,
                reason_code="verification_passed",
            ),
        )


def test_evidence_limit_is_enforced_for_generators():
    def many_references() -> Iterable[EvidenceReference]:
        for index in range(101):
            yield reference(f"evidence-{index:03d}")

    with pytest.raises(EvidenceInputError, match="At most 100"):
        evaluate_work_order_evidence(snapshot(), many_references(), registry_for())


@pytest.mark.parametrize("revision", [0, -1, True, 1.5])
def test_work_order_revision_must_be_a_positive_integer(revision):
    with pytest.raises(EvidenceInputError, match="revision"):
        evaluate_work_order_evidence(
            WorkOrderSnapshot(
                work_order_id="workorder-123",
                revision=revision,
                digest=WORK_ORDER_DIGEST,
                criteria=(WorkOrderCriterion("ac_001"),),
            ),
            [],
            registry_for(),
        )


def test_report_digest_is_deterministic_for_identical_inputs():
    first = evaluate_work_order_evidence(snapshot(), [reference()], registry_for())
    second = evaluate_work_order_evidence(snapshot(), [reference()], registry_for())

    assert first.report_digest == second.report_digest
