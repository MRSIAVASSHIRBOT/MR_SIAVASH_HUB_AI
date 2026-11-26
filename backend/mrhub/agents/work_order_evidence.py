"""Digest-bound, read-only evidence evaluation for versioned WorkOrders.

Evidence can be accepted only through a verifier registered by trusted application
code. Model output and caller-supplied status labels are never evidence.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

MAX_WORK_ORDER_CRITERIA = 12
MAX_EVIDENCE_REFERENCES = 100
MAX_IDENTIFIER_LENGTH = 80
MAX_SOURCE_REFERENCE_LENGTH = 160

_IDENTIFIER_PATTERN = re.compile(r"^[a-z][a-z0-9._:-]{0,79}$")
_CRITERION_ID_PATTERN = re.compile(r"^ac_[0-9]{3}$")
_SOURCE_REFERENCE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,159}$")
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class VerifierStatus(StrEnum):
    """Outcome returned by a trusted evidence verifier."""

    PASSED = "passed"
    FAILED = "failed"
    UNKNOWN = "unknown"


class CriterionEvidenceStatus(StrEnum):
    """Aggregated state of evidence attached to one WorkOrder criterion."""

    PASSED = "passed"
    FAILED = "failed"
    UNKNOWN = "unknown"
    STALE = "stale"
    CONFLICTING = "conflicting"


class WorkOrderDecision(StrEnum):
    """Conservative decision across all required WorkOrder criteria."""

    ACCEPT = "accept"
    REJECT = "reject"
    REVIEW_REQUIRED = "review_required"


@dataclass(frozen=True, slots=True)
class WorkOrderCriterion:
    """Stable criterion identity and server-derived verification constraints."""

    criterion_id: str
    required: bool = True
    description: str = ""
    step_capability_bindings: tuple[tuple[str, tuple[str, ...]], ...] = ()


@dataclass(frozen=True, slots=True)
class WorkOrderSnapshot:
    """Digest-bound identity and required criteria for one WorkOrder revision."""

    work_order_id: str
    revision: int
    digest: str
    criteria: tuple[WorkOrderCriterion, ...]


@dataclass(frozen=True, slots=True)
class EvidenceReference:
    """Opaque pointer to evidence; it contains no evidence payload or status claim."""

    evidence_id: str
    criterion_id: str
    source_type: str
    source_ref: str
    evidence_digest: str
    work_order_digest: str
    work_order_revision: int
    observed_at: str
    verifier_id: str
    # Internal server context; this field is not part of the HTTP request schema
    # or report serialization and is always injected from the authenticated actor.
    owner_user_id: str | None = None


@dataclass(frozen=True, slots=True)
class EvidenceVerification:
    """Result produced by a server-registered verifier after checking a reference."""

    status: VerifierStatus
    evidence_digest: str | None = None
    reason_code: str = "verification_unavailable"


EvidenceVerifier = Callable[
    [EvidenceReference, WorkOrderCriterion], EvidenceVerification
]


@dataclass(frozen=True, slots=True)
class CriterionEvidenceResult:
    """Privacy-minimized result for one criterion."""

    criterion_id: str
    required: bool
    status: CriterionEvidenceStatus
    evidence_ids: tuple[str, ...]
    reason_codes: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        """Return identifiers and bounded reason codes, never raw source references."""
        return {
            "criterion_id": self.criterion_id,
            "required": self.required,
            "status": self.status.value,
            "evidence_ids": list(self.evidence_ids),
            "reason_codes": list(self.reason_codes),
        }


@dataclass(frozen=True, slots=True)
class WorkOrderEvidenceReport:
    """Deterministic evaluation snapshot with no execution or permission side effects."""

    work_order_id: str
    work_order_revision: int
    work_order_digest: str
    decision: WorkOrderDecision
    criteria: tuple[CriterionEvidenceResult, ...]
    report_digest: str

    def as_dict(self) -> dict[str, object]:
        """Serialize the review result without exposing evidence payloads or source paths."""
        return {
            "schema_version": "work_order_evidence_report.v1",
            "work_order_id": self.work_order_id,
            "work_order_revision": self.work_order_revision,
            "work_order_digest": self.work_order_digest,
            "decision": self.decision.value,
            "criteria": [item.as_dict() for item in self.criteria],
            "report_digest": self.report_digest,
            "read_only": True,
            "execution_started": False,
            "permissions_changed": False,
            "automatic_retry": False,
            "automatic_correction": False,
        }


class EvidenceInputError(ValueError):
    """Raised when a WorkOrder or evidence reference violates the versioned contract."""


class EvidenceVerifierRegistry:
    """Resolve evidence verifiers registered by trusted server-side application code.

    The registry is intentionally in-memory and has no API for caller-provided
    verifier definitions. Production construction and registration belong to the
    Hub service composition root, not to a model response or public request.
    """

    def __init__(self) -> None:
        self._verifiers: dict[tuple[str, str], EvidenceVerifier] = {}

    def register(
        self,
        *,
        source_type: str,
        verifier_id: str,
        verifier: EvidenceVerifier,
    ) -> None:
        """Register one verifier for an exact source/verifier pair."""
        _validate_identifier(source_type, "source type")
        _validate_identifier(verifier_id, "verifier ID")
        if not callable(verifier):
            raise EvidenceInputError("Evidence verifier must be callable")
        key = (source_type, verifier_id)
        if key in self._verifiers:
            raise EvidenceInputError("Evidence verifier registration is duplicated")
        self._verifiers[key] = verifier

    def verify(
        self,
        reference: EvidenceReference,
        criterion: WorkOrderCriterion,
    ) -> EvidenceVerification:
        """Invoke only the verifier registered for the reference's exact source pair."""
        verifier = self._verifiers.get((reference.source_type, reference.verifier_id))
        if verifier is None:
            return EvidenceVerification(
                VerifierStatus.UNKNOWN,
                reason_code="unregistered_verifier",
            )
        try:
            result = verifier(reference, criterion)
        except Exception:  # noqa: BLE001 - a verifier failure must fail closed.
            return EvidenceVerification(
                VerifierStatus.UNKNOWN,
                reason_code="verifier_error",
            )
        return _normalize_verification(result, reference)


def _validate_identifier(value: object, label: str) -> str:
    """Validate a bounded lowercase identifier used in reports and registry keys."""
    if (
        not isinstance(value, str)
        or len(value) > MAX_IDENTIFIER_LENGTH
        or _IDENTIFIER_PATTERN.fullmatch(value) is None
    ):
        raise EvidenceInputError(f"{label} is invalid")
    return value


def _validate_sha256(value: object, label: str) -> str:
    """Accept only canonical lowercase SHA-256 hexadecimal digests."""
    if not isinstance(value, str) or _SHA256_PATTERN.fullmatch(value) is None:
        raise EvidenceInputError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _validate_timestamp(value: object) -> str:
    """Require a bounded ISO-8601 timestamp with an explicit timezone."""
    if not isinstance(value, str) or not 1 <= len(value) <= 40:
        raise EvidenceInputError("Evidence timestamp is invalid")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise EvidenceInputError("Evidence timestamp is invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise EvidenceInputError("Evidence timestamp requires an explicit timezone")
    return value


def _validate_snapshot(snapshot: WorkOrderSnapshot) -> dict[str, WorkOrderCriterion]:
    """Validate WorkOrder identity and return its unique criterion lookup."""
    if not isinstance(snapshot, WorkOrderSnapshot):
        raise TypeError("snapshot must be a WorkOrderSnapshot")
    _validate_identifier(snapshot.work_order_id, "WorkOrder ID")
    if (
        isinstance(snapshot.revision, bool)
        or not isinstance(snapshot.revision, int)
        or snapshot.revision < 1
    ):
        raise EvidenceInputError("WorkOrder revision must be a positive integer")
    _validate_sha256(snapshot.digest, "WorkOrder digest")
    if (
        not isinstance(snapshot.criteria, tuple)
        or not 1 <= len(snapshot.criteria) <= MAX_WORK_ORDER_CRITERIA
    ):
        raise EvidenceInputError("WorkOrder criteria must be a bounded non-empty tuple")

    by_id: dict[str, WorkOrderCriterion] = {}
    for criterion in snapshot.criteria:
        if not isinstance(criterion, WorkOrderCriterion):
            raise TypeError("Every WorkOrder criterion must be a WorkOrderCriterion")
        if (
            not isinstance(criterion.criterion_id, str)
            or _CRITERION_ID_PATTERN.fullmatch(criterion.criterion_id) is None
        ):
            raise EvidenceInputError("WorkOrder criterion ID is invalid")
        if type(criterion.required) is not bool:
            raise EvidenceInputError("WorkOrder criterion required flag must be boolean")
        if (
            not isinstance(criterion.description, str)
            or len(criterion.description) > 300
        ):
            raise EvidenceInputError("WorkOrder criterion description is invalid")
        if (
            not isinstance(criterion.step_capability_bindings, tuple)
            or len(criterion.step_capability_bindings) > MAX_WORK_ORDER_CRITERIA
        ):
            raise EvidenceInputError("WorkOrder criterion step/capability bindings are invalid")
        seen_step_ids: set[str] = set()
        for binding in criterion.step_capability_bindings:
            if (
                not isinstance(binding, tuple)
                or len(binding) != 2
                or not isinstance(binding[0], str)
                or re.fullmatch(r"^[a-z][a-z0-9_-]{0,39}$", binding[0]) is None
                or binding[0] in seen_step_ids
                or not isinstance(binding[1], tuple)
                or len(binding[1]) > MAX_WORK_ORDER_CRITERIA
            ):
                raise EvidenceInputError("WorkOrder criterion step/capability binding is invalid")
            seen_step_ids.add(binding[0])
            for capability in binding[1]:
                _validate_identifier(capability, "WorkOrder criterion capability")
        if criterion.criterion_id in by_id:
            raise EvidenceInputError("WorkOrder criterion IDs must be unique")
        by_id[criterion.criterion_id] = criterion
    if not any(criterion.required for criterion in by_id.values()):
        raise EvidenceInputError("At least one required WorkOrder criterion is required")
    return by_id


def _validate_reference(
    reference: EvidenceReference,
    criteria: dict[str, WorkOrderCriterion],
    seen_ids: set[str],
) -> None:
    """Validate one opaque evidence reference and bind it to a known criterion."""
    if not isinstance(reference, EvidenceReference):
        raise TypeError("Every evidence item must be an EvidenceReference")
    for value, label in (
        (reference.evidence_id, "Evidence ID"),
        (reference.source_type, "Evidence source type"),
        (reference.verifier_id, "Evidence verifier ID"),
    ):
        _validate_identifier(value, label)
    if reference.evidence_id in seen_ids:
        raise EvidenceInputError("Evidence IDs must be unique")
    seen_ids.add(reference.evidence_id)
    if (
        not isinstance(reference.criterion_id, str)
        or _CRITERION_ID_PATTERN.fullmatch(reference.criterion_id) is None
        or reference.criterion_id not in criteria
    ):
        raise EvidenceInputError("Evidence references an unknown WorkOrder criterion")
    if (
        not isinstance(reference.source_ref, str)
        or len(reference.source_ref) > MAX_SOURCE_REFERENCE_LENGTH
        or _SOURCE_REFERENCE_PATTERN.fullmatch(reference.source_ref) is None
    ):
        raise EvidenceInputError("Evidence source reference is invalid")
    _validate_sha256(reference.evidence_digest, "Evidence digest")
    _validate_sha256(reference.work_order_digest, "Evidence WorkOrder digest")
    if (
        isinstance(reference.work_order_revision, bool)
        or not isinstance(reference.work_order_revision, int)
        or reference.work_order_revision < 1
    ):
        raise EvidenceInputError("Evidence WorkOrder revision is invalid")
    _validate_timestamp(reference.observed_at)
    if reference.owner_user_id is not None and (
        not isinstance(reference.owner_user_id, str)
        or not reference.owner_user_id.strip()
        or len(reference.owner_user_id) > 200
    ):
        raise EvidenceInputError("Evidence owner context is invalid")


def _normalize_verification(
    value: object,
    reference: EvidenceReference,
) -> EvidenceVerification:
    """Reject malformed verifier results and digest mismatches as unknown evidence."""
    if not isinstance(value, EvidenceVerification):
        return EvidenceVerification(
            VerifierStatus.UNKNOWN,
            reason_code="invalid_verifier_response",
        )
    if not isinstance(value.status, VerifierStatus):
        return EvidenceVerification(
            VerifierStatus.UNKNOWN,
            reason_code="invalid_verifier_status",
        )
    if (
        not isinstance(value.reason_code, str)
        or _IDENTIFIER_PATTERN.fullmatch(value.reason_code) is None
    ):
        return EvidenceVerification(
            VerifierStatus.UNKNOWN,
            reason_code="invalid_reason_code",
        )
    if value.status is VerifierStatus.UNKNOWN:
        if value.evidence_digest is not None:
            return EvidenceVerification(
                VerifierStatus.UNKNOWN,
                reason_code="unknown_result_claims_digest",
            )
        return value
    if value.evidence_digest != reference.evidence_digest:
        return EvidenceVerification(
            VerifierStatus.UNKNOWN,
            reason_code="evidence_digest_mismatch",
        )
    return value


def _criterion_status(
    verifications: tuple[tuple[str, VerifierStatus], ...],
    stale_ids: tuple[str, ...],
) -> CriterionEvidenceStatus:
    """Aggregate only verifier-checked outcomes; stale or conflicting data cannot pass."""
    statuses = {status for _, status in verifications}
    if VerifierStatus.PASSED in statuses and VerifierStatus.FAILED in statuses:
        return CriterionEvidenceStatus.CONFLICTING
    if stale_ids:
        return CriterionEvidenceStatus.STALE
    if VerifierStatus.FAILED in statuses:
        return CriterionEvidenceStatus.FAILED
    if VerifierStatus.UNKNOWN in statuses or not statuses:
        return CriterionEvidenceStatus.UNKNOWN
    return CriterionEvidenceStatus.PASSED


def _report_digest(
    work_order_id: str,
    revision: int,
    work_order_digest: str,
    decision: WorkOrderDecision,
    criteria: tuple[CriterionEvidenceResult, ...],
) -> str:
    """Create a deterministic digest from the sanitized, ordered report body."""
    payload = {
        "schema_version": "work_order_evidence_report.v1",
        "work_order_id": work_order_id,
        "work_order_revision": revision,
        "work_order_digest": work_order_digest,
        "decision": decision.value,
        "criteria": [item.as_dict() for item in criteria],
        "read_only": True,
        "execution_started": False,
        "permissions_changed": False,
        "automatic_retry": False,
        "automatic_correction": False,
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def evaluate_work_order_evidence(
    snapshot: WorkOrderSnapshot,
    evidence: Iterable[EvidenceReference],
    verifiers: EvidenceVerifierRegistry,
) -> WorkOrderEvidenceReport:
    """Evaluate bounded evidence against one exact WorkOrder revision.

    A criterion passes only when every supplied reference is current, resolves
    through its registered trusted verifier, and the verifier confirms the same
    evidence digest. Missing, stale, conflicting, or unverifiable evidence cannot
    produce an accepted decision. This function is deterministic for identical
    verifier outputs and inputs; it never executes, retries, or mutates workflows.
    """
    criteria = _validate_snapshot(snapshot)
    if not isinstance(verifiers, EvidenceVerifierRegistry):
        raise TypeError("verifiers must be an EvidenceVerifierRegistry")
    if isinstance(evidence, (str, bytes)):
        raise EvidenceInputError("Evidence references must be an iterable of records")

    iterator = iter(evidence)
    references: list[EvidenceReference] = []
    for _ in range(MAX_EVIDENCE_REFERENCES + 1):
        try:
            references.append(next(iterator))
        except StopIteration:
            break
    if len(references) > MAX_EVIDENCE_REFERENCES:
        raise EvidenceInputError(
            f"At most {MAX_EVIDENCE_REFERENCES} evidence references are allowed"
        )

    seen_ids: set[str] = set()
    grouped: dict[str, list[EvidenceReference]] = {
        criterion_id: [] for criterion_id in criteria
    }
    for reference in references:
        _validate_reference(reference, criteria, seen_ids)
        grouped[reference.criterion_id].append(reference)

    results: list[CriterionEvidenceResult] = []
    for criterion in snapshot.criteria:
        current_verifications: list[tuple[str, VerifierStatus]] = []
        stale_ids: list[str] = []
        reason_codes: set[str] = set()
        evidence_ids: list[str] = []
        for reference in grouped[criterion.criterion_id]:
            evidence_ids.append(reference.evidence_id)
            if (
                reference.work_order_digest != snapshot.digest
                or reference.work_order_revision != snapshot.revision
            ):
                stale_ids.append(reference.evidence_id)
                reason_codes.add("stale_work_order_reference")
                continue
            verification = verifiers.verify(reference, criterion)
            current_verifications.append((reference.evidence_id, verification.status))
            reason_codes.add(verification.reason_code)

        status = _criterion_status(
            tuple(current_verifications),
            tuple(stale_ids),
        )
        results.append(CriterionEvidenceResult(
            criterion_id=criterion.criterion_id,
            required=criterion.required,
            status=status,
            evidence_ids=tuple(sorted(evidence_ids)),
            reason_codes=tuple(sorted(reason_codes)),
        ))

    frozen_results = tuple(results)
    required_statuses = tuple(item.status for item in frozen_results if item.required)
    if any(status is CriterionEvidenceStatus.FAILED for status in required_statuses):
        decision = WorkOrderDecision.REJECT
    elif all(status is CriterionEvidenceStatus.PASSED for status in required_statuses):
        decision = WorkOrderDecision.ACCEPT
    else:
        decision = WorkOrderDecision.REVIEW_REQUIRED

    digest = _report_digest(
        snapshot.work_order_id,
        snapshot.revision,
        snapshot.digest,
        decision,
        frozen_results,
    )
    return WorkOrderEvidenceReport(
        work_order_id=snapshot.work_order_id,
        work_order_revision=snapshot.revision,
        work_order_digest=snapshot.digest,
        decision=decision,
        criteria=frozen_results,
        report_digest=digest,
    )
