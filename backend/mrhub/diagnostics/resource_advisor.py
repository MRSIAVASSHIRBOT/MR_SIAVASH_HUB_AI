"""Conservative, deterministic estimates for local model resource fit.

The advisor consumes an explicit model profile. It does not query a registry,
download a model, start an inference server, or run inference.
"""

from __future__ import annotations

import math
from typing import Any

DEFAULT_SYSTEM_RESERVE_GIB = 2.0


def assess_model_resources(
    hardware_report: dict[str, Any],
    model_profile: dict[str, Any],
    *,
    system_reserve_gib: float = DEFAULT_SYSTEM_RESERVE_GIB,
) -> dict[str, Any]:
    """Assess RAM fit from declared requirements without guessing missing data.

    Required profile fields:
      - name: display name
      - minimum_ram_gib: estimated minimum runtime RAM
      - recommended_ram_gib: recommended runtime RAM
      - requires_gpu: whether this profile requires GPU acceleration

    RAM figures must come from a trusted model-specific source or an
    operator-provided estimate. This function does not validate their origin.
    """
    if (
        isinstance(system_reserve_gib, bool)
        or not isinstance(system_reserve_gib, (int, float))
        or not math.isfinite(system_reserve_gib)
        or system_reserve_gib < 0
    ):
        raise ValueError("system_reserve_gib must be a finite non-negative number")

    if not isinstance(hardware_report, dict) or not isinstance(model_profile, dict):
        return {
            "status": "invalid_profile",
            "model": None,
            "reasons": ["Hardware report and model profile must be objects."],
            "starts_inference": False,
        }

    name = model_profile.get("name")
    minimum = model_profile.get("minimum_ram_gib")
    recommended = model_profile.get("recommended_ram_gib")
    requires_gpu = model_profile.get("requires_gpu")
    valid_numbers = all(
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(value)
        for value in (minimum, recommended)
    )
    if (
        not isinstance(name, str)
        or not name.strip()
        or not valid_numbers
        or not isinstance(requires_gpu, bool)
        or minimum <= 0
        or recommended < minimum
    ):
        return {
            "status": "invalid_profile",
            "model": name if isinstance(name, str) else None,
            "reasons": [
                ("A valid name, positive finite minimum RAM, recommended RAM >= minimum, "
                "and requires_gpu flag are required.")
            ],
            "starts_inference": False,
        }

    memory = hardware_report.get("memory", {})
    available = memory.get("available_gib") if isinstance(memory, dict) else None
    if (
        isinstance(available, bool)
        or not isinstance(available, (int, float))
        or not math.isfinite(available)
        or available < 0
    ):
        return {
            "status": "insufficient_data",
            "model": name,
            "available_ram_gib": None,
            "usable_ram_gib": None,
            "system_reserve_gib": float(system_reserve_gib),
            "reasons": ["Currently available physical RAM was not reported."],
            "starts_inference": False,
        }

    usable = max(0.0, float(available) - float(system_reserve_gib))
    reasons = [
        "RAM fit is an estimate based on declared profile values, not a benchmark.",
        "Actual use varies with quantization, context length, runtime overhead, and concurrent applications.",
    ]

    if requires_gpu:
        gpu = hardware_report.get("gpu", {})
        reasons.append("GPU VRAM and compute capability are not measured by this diagnostic.")
        return {
            "status": "insufficient_data",
            "model": name,
            "available_ram_gib": round(float(available), 2),
            "usable_ram_gib": round(usable, 2),
            "system_reserve_gib": float(system_reserve_gib),
            "gpu_status": gpu.get("status", "unknown") if isinstance(gpu, dict) else "unknown",
            "reasons": reasons,
            "starts_inference": False,
        }

    if usable >= float(recommended):
        status = "likely_fit"
        reasons.append("Reported usable RAM meets the profile's recommended RAM estimate.")
    elif usable >= float(minimum):
        status = "likely_tight"
        reasons.append("Reported usable RAM meets only the profile's minimum RAM estimate.")
    else:
        status = "not_recommended"
        reasons.append("Reported usable RAM is below the profile's minimum RAM estimate.")

    return {
        "status": status,
        "model": name,
        "available_ram_gib": round(float(available), 2),
        "usable_ram_gib": round(usable, 2),
        "system_reserve_gib": float(system_reserve_gib),
        "minimum_ram_gib": float(minimum),
        "recommended_ram_gib": float(recommended),
        "reasons": reasons,
        "starts_inference": False,
    }
