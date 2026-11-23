"""Integrity-checked integration preview for reviewed plan revisions.

This module returns a structural preview only. It does not mutate plans,
execute steps, authorize tools, or treat caller-supplied review identity as auth.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from mrhub.agents.plan_revision import PlanRevisionInputError, PlanStep, _validate_dag
from mrhub.agents.revision_review import ReviewDecision, compare_revisions

MAX_STEPS = 100


class IntegrationInputError(ValueError):
    """Invalid integration-preview input."""


@dataclass(frozen=True)
class IntegrationPreview:
    revision: int
    digest: str
    steps: tuple[dict[str, object], ...]
    preserved_ids: tuple[str, ...]
    added_ids: tuple[str, ...]
    preview_only: bool = True
    review_required: bool = True


def _step_objects(plan: Mapping[str, object]) -> list[dict[str, object]]:
    raw = plan.get("steps")
    if not isinstance(raw, list) or len(raw) > MAX_STEPS:
        raise IntegrationInputError("Plan must contain a bounded steps list")
    normalized: list[dict[str, object]] = []
    for item in raw:
        if not isinstance(item, dict):
            raise IntegrationInputError("Each step must be a mapping")
        sid, desc, deps, status = item.get("step_id"), item.get("description"), item.get("dependencies", []), item.get("status", "pending")
        if not isinstance(sid, str) or not sid.strip() or not isinstance(desc, str) or not desc.strip():
            raise IntegrationInputError("Step ID and description must be non-empty strings")
        if len(sid) > 500 or len(desc) > 500 or not isinstance(deps, list) or not all(isinstance(d, str) for d in deps):
            raise IntegrationInputError("Invalid step fields")
        if status not in ("pending", "completed", "blocked"):
            raise IntegrationInputError("Unsupported step status")
        normalized.append({"step_id": sid, "description": desc, "dependencies": list(deps), "status": status})
    return normalized


def preview_integration(original: Mapping[str, object], candidate: Mapping[str, object], *,
                        decision: ReviewDecision) -> IntegrationPreview:
    """Validate approval binding and preservation invariants; return preview only."""
    if not isinstance(decision, ReviewDecision) or decision.approved is not True:
        raise IntegrationInputError("An affirmative review record is required")
    if not decision.digest or decision.revision < 1:
        raise IntegrationInputError("Invalid review record")
    old, new = _step_objects(original), _step_objects(candidate)
    old_by_id = {s["step_id"]: s for s in old}
    new_by_id = {s["step_id"]: s for s in new}
    if len(old_by_id) != len(old) or len(new_by_id) != len(new):
        raise IntegrationInputError("Duplicate step IDs")
    if len(new) > MAX_STEPS:
        raise IntegrationInputError("Candidate exceeds the supported step limit")
    # Original steps must remain byte-for-byte equivalent after normalization.
    for sid, step in old_by_id.items():
        if new_by_id.get(sid) != step:
            raise IntegrationInputError("Original steps must be preserved unchanged")
    added = sorted(set(new_by_id) - set(old_by_id))
    # Verify digest is tied to the exact candidate, revision, and current review.
    diff = compare_revisions(original, candidate, revision=decision.revision)
    if diff.digest != decision.digest:
        raise IntegrationInputError("Review digest does not match candidate")
    # Validate dependency structure without authorizing any step.
    typed = [PlanStep(s["step_id"], s["description"], tuple(s["dependencies"]), s["status"]) for s in new]
    try:
        _validate_dag(typed)
    except PlanRevisionInputError as exc:
        raise IntegrationInputError("Candidate dependency graph is invalid") from exc
    return IntegrationPreview(decision.revision, diff.digest, tuple(new),
                             tuple(sorted(old_by_id)), tuple(added))
