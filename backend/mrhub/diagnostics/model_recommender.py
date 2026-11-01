"""Advisory ranking for registered model profiles.

This module only ranks declared profiles using the deterministic resource
advisor. It never chooses a provider, starts inference, or downloads models.
"""
from __future__ import annotations

from typing import Any

from mrhub.diagnostics.model_profiles import get_model_profile
from mrhub.diagnostics.resource_advisor import assess_model_resources

_STATUS_RANK = {
    "likely_fit": 0,
    "likely_tight": 1,
    "insufficient_data": 2,
    "not_recommended": 3,
    "invalid_profile": 4,
}


def recommend_model_profiles(
    hardware_report: dict[str, Any],
    profile_ids: list[str],
    *,
    system_reserve_gib: float = 2.0,
) -> dict[str, Any]:
    """Rank known profiles by resource fit, keeping uncertainty explicit."""
    if not profile_ids:
        raise ValueError("At least one profile ID is required")
    if len(profile_ids) > 20:
        raise ValueError("At most 20 profile IDs may be compared")
    unique_ids = list(dict.fromkeys(profile_ids))

    unknown_ids = [
        profile_id for profile_id in unique_ids
        if get_model_profile(profile_id) is None
    ]
    if unknown_ids:
        raise KeyError(tuple(unknown_ids))

    results: list[dict[str, Any]] = []
    for profile_id in unique_ids:
        profile = get_model_profile(profile_id)
        assessment = assess_model_resources(
            hardware_report,
            {
                "name": profile["name"],
                "minimum_ram_gib": profile["minimum_ram_gib"],
                "recommended_ram_gib": profile["recommended_ram_gib"],
                "requires_gpu": profile["requires_gpu"],
            },
            system_reserve_gib=system_reserve_gib,
        )
        results.append({
            "profile_id": profile_id,
            "name": profile["name"],
            "verified": profile["verified"],
            "source_kind": profile["source_kind"],
            "assessment": assessment,
            "recommendation": (
                "candidate" if assessment["status"] in {"likely_fit", "likely_tight"}
                and not profile["requires_gpu"] else "not_recommended_or_unverified"
            ),
        })

    results.sort(key=lambda item: (
        _STATUS_RANK.get(item["assessment"]["status"], 99),
        item["profile_id"],
    ))
    return {
        "results": results,
        "count": len(results),
        "best_candidate_profile_id": next(
            (item["profile_id"] for item in results if item["recommendation"] == "candidate"),
            None,
        ),
        "decision_mode": "advisory_only",
        "starts_inference": False,
        "downloads_model": False,
        "selects_provider": False,
        "limitations": [
            "Registry entries are illustrative and currently unverified.",
            "RAM fit is an estimate; CPU throughput, context length, quantization, and runtime overhead are not benchmarked.",
            "GPU-required profiles remain non-candidates until GPU VRAM and compute data are measured.",
        ],
    }
