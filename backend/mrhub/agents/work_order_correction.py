"""Digest-bound, read-only correction proposals for WorkOrder evidence results.

The proposal layer identifies the next safe review action. It never changes a
WorkOrder, plan, workflow, permission, or execution state.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum

from mrhub.agents.work_order_evidence import (
    CriterionEvidenceStatus,
    WorkOrderDecision,
    WorkOrderEvidenceReport,
)


class CorrectionAction(StrEnum):
    """Non-executable action category suggested to the owner."""

    PREPARE_REVIEWED_CORRECTION = "prepare_reviewed_correction"
    GATHER_OR_RECONCILE_EVIDENCE = "gather_or_reconcile_evidence"


@dataclass(frozen=True, slots=True)
class CorrectionProposalItem:
    """Minimal, provenance-bound recommendation for one WorkOrder criterion."""

    criterion_id: str
    status: str
    evidence_ids: tuple[str, ...]
    reason_codes: tuple[str, ...]
    action: CorrectionAction

    def as_dict(self) -> dict[str, object]:
        return {
            "criterion_id": self.criterion_id,
            "status": self.status,
            "evidence_ids": list(self.evidence_ids),
            "reason_codes": list(self.reason_codes),
            "action": self.action.value,
        }


@dataclass(frozen=True, slots=True)
class WorkOrderCorrectionProposal:
    """Immutable read-only proposal bound to one exact evidence report digest."""

    work_order_id: str
    work_order_revision: int
    work_order_digest: str
    evidence_report_digest: str
    decision: str
    items: tuple[CorrectionProposalItem, ...]
    proposal_digest: str

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": "work_order_correction_proposal.v1",
            "work_order_id": self.work_order_id,
            "work_order_revision": self.work_order_revision,
            "work_order_digest": self.work_order_digest,
            "evidence_report_digest": self.evidence_report_digest,
            "decision": self.decision,
            "items": [item.as_dict() for item in self.items],
            "proposal_digest": self.proposal_digest,
            "read_only": True,
            "requires_owner_review": True,
            "plan_revision_created": False,
            "workflow_changed": False,
            "execution_started": False,
            "automatic_retry": False,
            "permissions_changed": False,
        }


def build_work_order_correction_proposal(
    report: WorkOrderEvidenceReport,
) -> WorkOrderCorrectionProposal:
    """Build deterministic, digest-bound review guidance without side effects."""
    if not isinstance(report, WorkOrderEvidenceReport):
        raise TypeError("report must be a WorkOrderEvidenceReport")

    items: list[CorrectionProposalItem] = []
    for criterion in report.criteria:
        if not criterion.required or criterion.status is CriterionEvidenceStatus.PASSED:
            continue
        action = (
            CorrectionAction.PREPARE_REVIEWED_CORRECTION
            if criterion.status is CriterionEvidenceStatus.FAILED
            else CorrectionAction.GATHER_OR_RECONCILE_EVIDENCE
        )
        items.append(
            CorrectionProposalItem(
                criterion_id=criterion.criterion_id,
                status=criterion.status.value,
                evidence_ids=tuple(sorted(criterion.evidence_ids)),
                reason_codes=tuple(sorted(criterion.reason_codes)),
                action=action,
            )
        )

    body: dict[str, object] = {
        "schema_version": "work_order_correction_proposal.v1",
        "work_order_id": report.work_order_id,
        "work_order_revision": report.work_order_revision,
        "work_order_digest": report.work_order_digest,
        "evidence_report_digest": report.report_digest,
        "decision": report.decision.value,
        "items": [item.as_dict() for item in items],
        "read_only": True,
        "requires_owner_review": True,
        "plan_revision_created": False,
        "workflow_changed": False,
        "execution_started": False,
        "automatic_retry": False,
        "permissions_changed": False,
    }
    encoded = json.dumps(
        body,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    digest = hashlib.sha256(encoded).hexdigest()
    return WorkOrderCorrectionProposal(
        work_order_id=report.work_order_id,
        work_order_revision=report.work_order_revision,
        work_order_digest=report.work_order_digest,
        evidence_report_digest=report.report_digest,
        decision=report.decision.value,
        items=tuple(items),
        proposal_digest=digest,
    )
