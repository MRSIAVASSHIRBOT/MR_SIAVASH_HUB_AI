from dataclasses import replace

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

WORK_ORDER_ID = "wo_release_001"
WORK_ORDER_DIGEST = "a" * 64
EVIDENCE_DIGEST_A = "b" * 64
EVIDENCE_DIGEST_B = "c" * 64
OBSERVED_AT = "2026-11-25T10:00:00+00:00"


def _snapshot():
    return WorkOrderSnapshot(
        work_order_id=WORK_ORDER_ID,
        revision=1,
        digest=WORK_ORDER_DIGEST,
        criteria=(
            WorkOrderCriterion("ac_001"),
            WorkOrderCriterion("ac_002"),
        ),
    )


def _reference(
    evidence_id="evidence_001",
    criterion_id="ac_001",
    *,
    digest=EVIDENCE_DIGEST_A,
    work_order_digest=WORK_ORDER_DIGEST,
    revision=1,
    source_type="artifact",
    verifier_id="artifact.checksum",
):
    return EvidenceReference(
        evidence_id=evidence_id,
        criterion_id=criterion_id,
        source_type=source_type,
        source_ref="artifact:sha256:sample-001",
        evidence_digest=digest,
        work_order_digest=work_order_digest,
        work_order_revision=revision,
        observed_at=OBSERVED_AT,
        verifier_id=verifier_id,
    )


def _registry(status=VerifierStatus.PASSED):
    registry = EvidenceVerifierRegistry()

    def verify(reference, _criterion):
        if status is VerifierStatus.UNKNOWN:
            return EvidenceVerification(
                status=status,
                reason_code="verification_unavailable",
            )
        reason_code = (
            "artifact_verified"
            if status is VerifierStatus.PASSED
            else "artifact_failed"
        )
        return EvidenceVerification(
            status=status,
            evidence_digest=reference.evidence_digest,
            reason_code=reason_code,
        )

    registry.register(
        source_type="artifact",
        verifier_id="artifact.checksum",
        verifier=verify,
    )
    return registry


def test_all_required_criteria_accept_only_after_registered_verification():
    report = evaluate_work_order_evidence(
        _snapshot(),
        (
            _reference("evidence_001", "ac_001"),
            _reference("evidence_002", "ac_002", digest=EVIDENCE_DIGEST_B),
        ),
        _registry(),
    )

    assert report.decision is WorkOrderDecision.ACCEPT
    assert all(item.status is CriterionEvidenceStatus.PASSED for item in report.criteria)
    assert len(report.report_digest) == 64
    rendered = report.as_dict()
    assert rendered["read_only"] is True
    assert rendered["execution_started"] is False
    assert rendered["permissions_changed"] is False
    assert "artifact:sha256:sample-001" not in str(rendered)


def test_missing_or_unregistered_evidence_requires_review():
    report = evaluate_work_order_evidence(
        _snapshot(),
        (_reference(),),
        EvidenceVerifierRegistry(),
    )

    assert report.decision is WorkOrderDecision.REVIEW_REQUIRED
    assert report.criteria[0].status is CriterionEvidenceStatus.UNKNOWN
    assert report.criteria[1].status is CriterionEvidenceStatus.UNKNOWN
    assert "unregistered_verifier" in report.criteria[0].reason_codes


def test_verified_failure_rejects_required_criterion():
    report = evaluate_work_order_evidence(
        _snapshot(),
        (_reference(),),
        _registry(VerifierStatus.FAILED),
    )

    assert report.decision is WorkOrderDecision.REJECT
    assert report.criteria[0].status is CriterionEvidenceStatus.FAILED
    assert report.criteria[1].status is CriterionEvidenceStatus.UNKNOWN


def test_stale_work_order_digest_or_revision_never_passes():
    stale = _reference(work_order_digest="d" * 64, revision=2)
    report = evaluate_work_order_evidence(_snapshot(), (stale,), _registry())

    assert report.decision is WorkOrderDecision.REVIEW_REQUIRED
    assert report.criteria[0].status is CriterionEvidenceStatus.STALE
    assert "stale_work_order_reference" in report.criteria[0].reason_codes


def test_conflicting_verified_evidence_requires_review():
    registry = EvidenceVerifierRegistry()
    registry.register(
        source_type="artifact",
        verifier_id="artifact.pass",
        verifier=lambda reference, _criterion: EvidenceVerification(
            VerifierStatus.PASSED, reference.evidence_digest, "artifact_passed"
        ),
    )
    registry.register(
        source_type="artifact",
        verifier_id="artifact.fail",
        verifier=lambda reference, _criterion: EvidenceVerification(
            VerifierStatus.FAILED, reference.evidence_digest, "artifact_failed"
        ),
    )
    references = (
        _reference("evidence_pass", verifier_id="artifact.pass"),
        _reference("evidence_fail", verifier_id="artifact.fail", digest=EVIDENCE_DIGEST_B),
    )

    report = evaluate_work_order_evidence(_snapshot(), references, registry)

    assert report.decision is WorkOrderDecision.REVIEW_REQUIRED
    assert report.criteria[0].status is CriterionEvidenceStatus.CONFLICTING


def test_verifier_exception_and_digest_mismatch_fail_closed():
    registry = EvidenceVerifierRegistry()

    def fail_offline(_reference, _criterion):
        raise RuntimeError("offline")

    registry.register(
        source_type="artifact",
        verifier_id="artifact.raises",
        verifier=fail_offline,
    )
    registry.register(
        source_type="artifact",
        verifier_id="artifact.wrong-digest",
        verifier=lambda _reference, _criterion: EvidenceVerification(
            VerifierStatus.PASSED, "e" * 64, "artifact_verified"
        ),
    )

    exception_report = evaluate_work_order_evidence(
        _snapshot(),
        (_reference(verifier_id="artifact.raises"),),
        registry,
    )
    mismatch_report = evaluate_work_order_evidence(
        _snapshot(),
        (_reference(verifier_id="artifact.wrong-digest"),),
        registry,
    )

    assert exception_report.decision is WorkOrderDecision.REVIEW_REQUIRED
    assert exception_report.criteria[0].status is CriterionEvidenceStatus.UNKNOWN
    assert mismatch_report.decision is WorkOrderDecision.REVIEW_REQUIRED
    assert mismatch_report.criteria[0].status is CriterionEvidenceStatus.UNKNOWN
    assert "evidence_digest_mismatch" in mismatch_report.criteria[0].reason_codes


def test_unknown_verifier_result_cannot_claim_an_evidence_digest():
    registry = EvidenceVerifierRegistry()
    registry.register(
        source_type="artifact",
        verifier_id="artifact.invalid",
        verifier=lambda reference, _criterion: EvidenceVerification(
            VerifierStatus.UNKNOWN,
            reference.evidence_digest,
            "verification_unavailable",
        ),
    )

    report = evaluate_work_order_evidence(
        _snapshot(),
        (_reference(verifier_id="artifact.invalid"),),
        registry,
    )

    assert report.decision is WorkOrderDecision.REVIEW_REQUIRED
    assert "unknown_result_claims_digest" in report.criteria[0].reason_codes


def test_optional_criterion_does_not_block_required_acceptance():
    snapshot = replace(
        _snapshot(),
        criteria=(
            WorkOrderCriterion("ac_001", required=True),
            WorkOrderCriterion("ac_002", required=False),
        ),
    )
    report = evaluate_work_order_evidence(
        snapshot,
        (_reference(),),
        _registry(),
    )

    assert report.decision is WorkOrderDecision.ACCEPT
    assert report.criteria[1].status is CriterionEvidenceStatus.UNKNOWN
    assert report.criteria[1].required is False


def test_report_digest_is_independent_of_evidence_input_order():
    references = (
        _reference("evidence_001", "ac_001"),
        _reference("evidence_002", "ac_002", digest=EVIDENCE_DIGEST_B),
    )
    first = evaluate_work_order_evidence(_snapshot(), references, _registry())
    second = evaluate_work_order_evidence(
        _snapshot(), tuple(reversed(references)), _registry()
    )

    assert first.report_digest == second.report_digest
    assert first.as_dict() == second.as_dict()


@pytest.mark.parametrize(
    "mutate",
    [
        lambda reference: replace(reference, evidence_digest="not-a-digest"),
        lambda reference: replace(reference, work_order_revision=True),
        lambda reference: replace(reference, observed_at="2026-11-25T10:00:00"),
        lambda reference: replace(
            reference, source_ref="https://example.test/?token=secret"
        ),
        lambda reference: replace(reference, criterion_id="ac_999"),
    ],
)
def test_malformed_evidence_references_are_rejected(mutate):
    reference = mutate(_reference())
    with pytest.raises(EvidenceInputError):
        evaluate_work_order_evidence(_snapshot(), (reference,), _registry())


def test_duplicate_evidence_ids_and_oversized_batches_are_rejected():
    duplicate = _reference("same")
    with pytest.raises(EvidenceInputError, match="unique"):
        evaluate_work_order_evidence(
            _snapshot(),
            (duplicate, replace(duplicate, criterion_id="ac_002")),
            _registry(),
        )

    with pytest.raises(EvidenceInputError, match="At most"):
        evaluate_work_order_evidence(
            _snapshot(),
            tuple(_reference(f"evidence_{index:03d}") for index in range(101)),
            _registry(),
        )


def test_duplicate_verifier_registration_is_rejected():
    registry = _registry()
    with pytest.raises(EvidenceInputError, match="duplicated"):
        registry.register(
            source_type="artifact",
            verifier_id="artifact.checksum",
            verifier=lambda _reference, _criterion: EvidenceVerification(
                VerifierStatus.UNKNOWN
            ),
        )


def test_work_order_requires_at_least_one_required_criterion():
    snapshot = replace(
        _snapshot(),
        criteria=(
            WorkOrderCriterion("ac_001", required=False),
            WorkOrderCriterion("ac_002", required=False),
        ),
    )

    with pytest.raises(EvidenceInputError, match="required"):
        evaluate_work_order_evidence(snapshot, (), EvidenceVerifierRegistry())
