"""Deterministic triage signals for public GitHub capability candidates.

This is a prioritization aid only. It is not a security audit and never approves
or activates a repository.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


def evaluate_repository_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    """Return bounded, explainable metadata-only triage without trusting repo code."""
    score = 50
    signals: list[dict[str, str]] = []
    license_data = metadata.get("license")
    license_id = (
        license_data.get("spdx_id")
        if isinstance(license_data, dict) and isinstance(license_data.get("spdx_id"), str)
        else None
    )
    if license_id and license_id not in {"", "NOASSERTION"}:
        score += 15
        signals.append({"code": "license_declared", "effect": "positive", "detail": "GitHub reports an SPDX license identifier."})
    else:
        score -= 20
        signals.append({"code": "license_unknown", "effect": "negative", "detail": "No recognized SPDX license identifier was reported."})

    if metadata.get("archived") is True or metadata.get("disabled") is True:
        score -= 35
        signals.append({"code": "repository_inactive", "effect": "negative", "detail": "Repository is archived or disabled."})
    if metadata.get("fork") is True:
        score -= 5
        signals.append({"code": "repository_is_fork", "effect": "caution", "detail": "Repository is a fork; upstream provenance needs review."})

    stars = metadata.get("stargazers_count")
    if isinstance(stars, int) and not isinstance(stars, bool):
        if stars >= 1000:
            score += 10
            signals.append({"code": "community_signal", "effect": "positive", "detail": "At least 1,000 stars; popularity is not a security guarantee."})
        elif stars < 5:
            score -= 5
            signals.append({"code": "limited_adoption_signal", "effect": "caution", "detail": "Fewer than five stars; assess project maturity manually."})

    updated_at = metadata.get("updated_at")
    if isinstance(updated_at, str) and updated_at:
        try:
            updated = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
            if updated.tzinfo is None:
                updated = updated.replace(tzinfo=UTC)
            age_days = max(0, (datetime.now(UTC) - updated.astimezone(UTC)).days)
            if age_days > 730:
                score -= 10
                signals.append({"code": "stale_repository", "effect": "caution", "detail": "No repository update has been reported for over two years."})
            elif age_days <= 180:
                score += 5
                signals.append({"code": "recent_activity", "effect": "positive", "detail": "Repository metadata reports an update within six months."})
        except ValueError:
            signals.append({"code": "invalid_updated_at", "effect": "caution", "detail": "Repository update timestamp could not be interpreted."})

    score = max(0, min(100, score))
    if metadata.get("archived") is True or metadata.get("disabled") is True or not license_id or license_id in {"", "NOASSERTION"}:
        recommendation = "manual_review_required"
    elif score >= 70:
        recommendation = "prioritize_review"
    else:
        recommendation = "standard_review"
    return {
        "score": score,
        "recommendation": recommendation,
        "signals": signals,
        "scope": "metadata_only",
        "security_audit_completed": False,
        "approval_granted": False,
        "installation_started": False,
        "source_code_executed": False,
    }
