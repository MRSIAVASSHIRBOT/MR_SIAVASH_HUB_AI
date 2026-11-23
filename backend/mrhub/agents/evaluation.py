"""Evidence-aware deterministic evaluation of workflow acceptance criteria.

This module evaluates structured outcomes supplied by trusted application code.
It does not ask a language model to certify its own work and does not execute
or retry workflow steps.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

MAX_CRITERIA = 100
MAX_ID_LENGTH = 64
MAX_DESCRIPTION_LENGTH = 500
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class CriterionStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    UNKNOWN = "unknown"


class EvaluationDecision(StrEnum):
    ACCEPT = "accept"
    REJECT = "reject"
    REVIEW_REQUIRED = "review_required"


@dataclass(frozen=True)
class EvaluationCriterion:
    criterion_id: str
    description: str
    status: CriterionStatus
    evidence_digest: str | None = None


@dataclass(frozen=True)
class EvaluationReport:
    decision: EvaluationDecision
    total: int
    passed: int
    failed: int
    unknown: int
    criteria: tuple[EvaluationCriterion, ...]

    @property
    def score(self) -> float:
        """Return the passed fraction; unknown criteria are not counted as passed."""
        return self.passed / self.total if self.total else 0.0

    @property
    def complete(self) -> bool:
        return self.unknown == 0

    def as_dict(self) -> dict[str, object]:
        return {
            "decision": self.decision.value,
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "unknown": self.unknown,
            "score": self.score,
            "complete": self.complete,
            "criteria": [
                {
                    "criterion_id": item.criterion_id,
                    "description": item.description,
                    "status": item.status.value,
                    "evidence_digest": item.evidence_digest,
                }
                for item in self.criteria
            ],
        }


class EvaluationInputError(ValueError):
    """Raised when evaluation criteria are malformed or lack required evidence."""


def build_correction_plan(report: EvaluationReport) -> dict[str, object]:
    """Derive bounded, non-executing follow-up work from verified criterion states.

    Failed criteria produce repair recommendations; unknown criteria produce
    evidence/reconciliation recommendations. The function never dispatches
    tools, mutates workflow state, or reclassifies missing evidence as success.
    """
    if not isinstance(report, EvaluationReport):
        raise TypeError("report must be an EvaluationReport")

    actions: list[dict[str, object]] = []
    for criterion in report.criteria:
        if criterion.status is CriterionStatus.FAILED:
            actions.append(
                {
                    "criterion_id": criterion.criterion_id,
                    "priority": "high",
                    "action": "repair_failed_criterion",
                    "description": criterion.description,
                    "recommended_next_step": (
                        "Inspect the failed checkpoint and its evidence, correct the "
                        "underlying cause, then create a revised plan with explicit "
                        "verification before any retry."
                    ),
                    "evidence_digest": criterion.evidence_digest,
                    "requires_replan": True,
                    "automatic_execution": False,
                }
            )
        elif criterion.status is CriterionStatus.UNKNOWN:
            actions.append(
                {
                    "criterion_id": criterion.criterion_id,
                    "priority": "normal",
                    "action": "collect_or_reconcile_evidence",
                    "description": criterion.description,
                    "recommended_next_step": (
                        "Collect independent evidence or explicitly reconcile the "
                        "checkpoint. Do not replay an ambiguous side effect merely "
                        "because its outcome is unknown."
                    ),
                    "evidence_digest": None,
                    "requires_replan": False,
                    "automatic_execution": False,
                }
            )

    decision = (
        "no_correction_required"
        if report.decision is EvaluationDecision.ACCEPT
        else "repair_and_replan"
        if report.decision is EvaluationDecision.REJECT
        else "evidence_review_required"
    )
    return {
        "decision": decision,
        "source_evaluation_decision": report.decision.value,
        "total_actions": len(actions),
        "actions": actions,
        "execution_started": False,
        "workflow_mutated": False,
        "limitations": [
            "Recommendations are deterministic templates, not a diagnosis of root cause.",
            "Unknown outcomes require explicit evidence or reconciliation.",
            "No retry, tool invocation, approval, or permission change occurs here.",
        ],
    }


def evaluate_criteria(criteria: Iterable[EvaluationCriterion]) -> EvaluationReport:
    """Evaluate structured criterion outcomes without inferring missing evidence.

    A passed or failed outcome must carry a SHA-256 digest that identifies its
    supporting evidence. Unknown outcomes must not carry a digest. A report is
    accepted only when every criterion passed; failures reject and unknowns
    require review.
    """
    iterator = iter(criteria)
    bounded_items: list[EvaluationCriterion] = []
    for _ in range(MAX_CRITERIA + 1):
        try:
            bounded_items.append(next(iterator))
        except StopIteration:
            break
    if len(bounded_items) > MAX_CRITERIA:
        raise EvaluationInputError(
            f"At most {MAX_CRITERIA} acceptance criteria are allowed"
        )
    items = tuple(bounded_items)
    if not items:
        raise EvaluationInputError("At least one acceptance criterion is required")
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, EvaluationCriterion):
            raise TypeError("Every criterion must be an EvaluationCriterion")
        if not isinstance(item.criterion_id, str):
            raise EvaluationInputError("Criterion identifiers must be strings")
        identifier = item.criterion_id.strip()
        if not identifier or len(identifier) > MAX_ID_LENGTH:
            raise EvaluationInputError(
                f"Criterion identifiers must contain 1 to {MAX_ID_LENGTH} characters"
            )
        if identifier != item.criterion_id:
            raise EvaluationInputError("Criterion identifiers cannot have surrounding whitespace")
        if identifier in seen:
            raise EvaluationInputError(f"Duplicate criterion identifier: {identifier}")
        seen.add(identifier)
        if not isinstance(item.description, str) or not item.description.strip():
            raise EvaluationInputError(f"Criterion {identifier} requires a description")
        if len(item.description) > MAX_DESCRIPTION_LENGTH:
            raise EvaluationInputError(f"Criterion {identifier} description is too long")
        if not isinstance(item.status, CriterionStatus):
            raise EvaluationInputError(f"Criterion {identifier} has an invalid status")
        if item.status is CriterionStatus.UNKNOWN:
            if item.evidence_digest is not None:
                raise EvaluationInputError(
                    f"Unknown criterion {identifier} cannot claim evidence"
                )
        elif (
            not isinstance(item.evidence_digest, str)
            or _SHA256_PATTERN.fullmatch(item.evidence_digest) is None
        ):
            raise EvaluationInputError(
                f"Criterion {identifier} requires a lowercase SHA-256 evidence digest"
            )

    passed = sum(item.status is CriterionStatus.PASSED for item in items)
    failed = sum(item.status is CriterionStatus.FAILED for item in items)
    unknown = sum(item.status is CriterionStatus.UNKNOWN for item in items)
    decision = (
        EvaluationDecision.REJECT
        if failed
        else EvaluationDecision.REVIEW_REQUIRED
        if unknown
        else EvaluationDecision.ACCEPT
    )
    return EvaluationReport(
        decision=decision,
        total=len(items),
        passed=passed,
        failed=failed,
        unknown=unknown,
        criteria=items,
    )
