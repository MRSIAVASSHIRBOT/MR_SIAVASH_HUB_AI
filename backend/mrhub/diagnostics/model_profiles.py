"""Small, explicit model-profile registry for resource planning.

Entries are illustrative operator estimates, not compatibility guarantees.
No network access or model download is performed.
"""
from __future__ import annotations

from typing import Any

_PROFILE_DATA: tuple[dict[str, Any], ...] = (
    {
        "id": "small-text-cpu-example",
        "name": "Small text model (operator estimate)",
        "minimum_ram_gib": 4.0,
        "recommended_ram_gib": 8.0,
        "requires_gpu": False,
        "source_kind": "operator_estimate",
        "verified": False,
        "notes": "Illustrative planning profile only; replace with requirements for the exact model, quantization, and context length.",
    },
    {
        "id": "gpu-model-example",
        "name": "GPU model (requirements not verified)",
        "minimum_ram_gib": 8.0,
        "recommended_ram_gib": 16.0,
        "requires_gpu": True,
        "source_kind": "operator_estimate",
        "verified": False,
        "notes": "Illustrative profile only; GPU VRAM and compute capability are not measured by the current host diagnostic.",
    },
)


def list_model_profiles() -> list[dict[str, Any]]:
    """Return defensive copies so callers cannot mutate the internal catalog."""
    return [dict(item) for item in _PROFILE_DATA]


def get_model_profile(profile_id: str) -> dict[str, Any] | None:
    """Return one defensive copy by stable profile ID."""
    for item in _PROFILE_DATA:
        if item["id"] == profile_id:
            return dict(item)
    return None
