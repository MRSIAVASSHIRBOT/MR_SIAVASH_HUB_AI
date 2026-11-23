"""Deterministic, advisory gap detection from AWI evaluation reports.

This module produces reviewable replanning suggestions only. It never executes
steps, calls tools, or treats missing evidence as proof of failure.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Mapping

MAX_GAPS = 100
MAX_TEXT_LENGTH = 500


class GapKind(StrEnum):
    FAILED = "failed"
    UNVERIFIED = "unverified"


@dataclass(frozen=True)
class CriterionGap:
    criterion_id: str
    description: str
    kind: GapKind
    evidence_digest: str | None


@dataclass(frozen=True)
class ReplanProposal:
    decision: str
    gaps: tuple[CriterionGap, ...]
    summary: str
    recommendations: tuple[str, ...]

    @property
    def needs_replanning(self) -> bool:
        return bool(self.gaps)


class ReplanningInputError(ValueError):
    """Raised for malformed or unbounded evaluation reports."""


def propose_replan(report: Mapping[str, object]) -> ReplanProposal:
    """Derive bounded, non-executable recommendations from a structured report.

    The report is treated as data: only known statuses and bounded text fields
    are used. Recommendations are generic and require human review.
    """
    raw_criteria = report.get("criteria")
    if not isinstance(raw_criteria, list) or not raw_criteria:
        raise ReplanningInputError("Report must contain a non-empty criteria list")
    if len(raw_criteria) > MAX_GAPS:
        raise ReplanningInputError("Report exceeds supported criteria limit")

    gaps: list[CriterionGap] = []
    seen: set[str] = set()
    for raw in raw_criteria:
        if not isinstance(raw, dict):
            raise ReplanningInputError("Criterion entries must be mappings")
        criterion_id = raw.get("criterion_id")
        description = raw.get("description")
        status = raw.get("status")
        digest = raw.get("evidence_digest")
        if (
            not isinstance(criterion_id, str)
            or not criterion_id.strip()
            or len(criterion_id) > MAX_TEXT_LENGTH
            or criterion_id != criterion_id.strip()
        ):
            raise ReplanningInputError("Invalid criterion identifier")
        if criterion_id in seen:
            raise ReplanningInputError("Duplicate criterion identifier")
        seen.add(criterion_id)
        if not isinstance(description, str) or not description.strip() or len(description) > MAX_TEXT_LENGTH:
            raise ReplanningInputError("Invalid criterion description")
        if status not in ("passed", "failed", "unknown"):
            raise ReplanningInputError("Unsupported criterion status")
        if status == "passed":
            continue
        if status == "failed":
            if not isinstance(digest, str) or len(digest) != 64:
                raise ReplanningInputError("Failed criteria require an evidence digest")
            kind = GapKind.FAILED
        else:
            if digest is not None:
                raise ReplanningInputError("Unknown criteria cannot claim evidence")
            kind = GapKind.UNVERIFIED
        gaps.append(CriterionGap(criterion_id, description, kind, digest))

    recommendations = tuple(
        "Review the failed criterion's evidence and adjust the plan before any retry."
        if gap.kind is GapKind.FAILED
        else "Collect verifiable evidence for this criterion before marking it complete."
        for gap in gaps
    )
    decision = report.get("decision", "review_required")
    if not isinstance(decision, str) or len(decision) > 40:
        raise ReplanningInputError("Invalid report decision")
    summary = (
        "All criteria passed; no replanning is suggested."
        if not gaps
        else f"{len(gaps)} criterion gap(s) require review; no actions were executed."
    )
    return ReplanProposal(decision, tuple(gaps), summary, recommendations)
