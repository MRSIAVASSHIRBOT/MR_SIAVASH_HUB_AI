"""Plan revision diff and explicit review decision records (proposal-only)."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Mapping

MAX_STEPS = 100
MAX_TEXT = 500


class ReviewInputError(ValueError):
    """Invalid revision comparison or review record."""


@dataclass(frozen=True)
class RevisionDiff:
    revision: int
    digest: str
    added: tuple[str, ...]
    removed: tuple[str, ...]
    changed: tuple[str, ...]
    unchanged: tuple[str, ...]
    review_required: bool = True


@dataclass(frozen=True)
class ReviewDecision:
    revision: int
    digest: str
    reviewer: str
    approved: bool
    note: str


def _canonical(plan: Mapping[str, object]) -> dict[str, dict[str, object]]:
    raw = plan.get("steps")
    if not isinstance(raw, list) or len(raw) > MAX_STEPS:
        raise ReviewInputError("Plan steps must be a bounded list")
    result: dict[str, dict[str, object]] = {}
    for step in raw:
        if not isinstance(step, dict):
            raise ReviewInputError("Step must be a mapping")
        sid = step.get("step_id")
        description = step.get("description")
        deps = step.get("dependencies", [])
        status = step.get("status", "pending")
        if not isinstance(sid, str) or not sid.strip() or len(sid) > MAX_TEXT:
            raise ReviewInputError("Invalid step ID")
        if sid in result:
            raise ReviewInputError("Duplicate step ID")
        if not isinstance(description, str) or not description.strip() or len(description) > MAX_TEXT:
            raise ReviewInputError("Invalid description")
        if not isinstance(deps, list) or not all(isinstance(x, str) for x in deps):
            raise ReviewInputError("Invalid dependencies")
        if status not in ("pending", "completed", "blocked"):
            raise ReviewInputError("Invalid status")
        result[sid] = {"description": description, "dependencies": sorted(deps), "status": status}
    return result


def compare_revisions(old_plan: Mapping[str, object], new_plan: Mapping[str, object], *, revision: int) -> RevisionDiff:
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
        raise ReviewInputError("Revision must be positive")
    old, new = _canonical(old_plan), _canonical(new_plan)
    old_ids, new_ids = set(old), set(new)
    added = tuple(sorted(new_ids - old_ids))
    removed = tuple(sorted(old_ids - new_ids))
    changed = tuple(sorted(sid for sid in old_ids & new_ids if old[sid] != new[sid]))
    unchanged = tuple(sorted(sid for sid in old_ids & new_ids if old[sid] == new[sid]))
    serialized = json.dumps({"revision": revision, "steps": new}, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    return RevisionDiff(revision, digest, added, removed, changed, unchanged)


def record_review(diff: RevisionDiff, *, reviewer: str, approved: bool, note: str = "") -> ReviewDecision:
    """Record a review decision bound to the exact proposal digest; never execute."""
    if not isinstance(diff, RevisionDiff) or not diff.review_required:
        raise ReviewInputError("A review-required diff is needed")
    if not isinstance(reviewer, str) or not reviewer.strip() or len(reviewer) > MAX_TEXT:
        raise ReviewInputError("Reviewer identity is required")
    if not isinstance(approved, bool):
        raise ReviewInputError("Decision must be explicitly boolean")
    if not isinstance(note, str) or len(note) > MAX_TEXT:
        raise ReviewInputError("Review note too long")
    return ReviewDecision(diff.revision, diff.digest, reviewer.strip(), approved, note)
