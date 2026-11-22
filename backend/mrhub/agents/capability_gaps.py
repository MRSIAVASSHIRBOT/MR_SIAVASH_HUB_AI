"""Deterministic CGI capability-gap evaluation against registered tools.

This evaluator reports gaps only. It does not discover, install, grant, or execute
capabilities; descriptions are not treated as executable capability identifiers.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

MAX_REQUIRED_CAPABILITIES = 50
MAX_TOOL_CATALOG_ENTRIES = 200
MAX_NAME_LENGTH = 80


@dataclass(frozen=True)
class CapabilityGapReport:
    required: tuple[str, ...]
    available: tuple[str, ...]
    missing: tuple[str, ...]

    @property
    def complete(self) -> bool:
        return not self.missing

    def as_dict(self) -> dict[str, object]:
        return {
            "required": list(self.required),
            "available": list(self.available),
            "missing": list(self.missing),
            "complete": self.complete,
        }


def _normalize_name(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field} must be a string")
    normalized = value.strip()
    if not normalized or len(normalized) > MAX_NAME_LENGTH:
        raise ValueError(f"{field} must contain 1 to {MAX_NAME_LENGTH} characters")
    return normalized.casefold()


def evaluate_capability_gaps(
    required_capabilities: Iterable[str],
    tool_catalog: Iterable[Mapping[str, object]],
) -> CapabilityGapReport:
    """Compare required capability identifiers with registered tool names.

    Exact, case-insensitive name matching is intentionally conservative. Tool
    descriptions are informational and cannot satisfy a requirement.
    """
    required: list[str] = []
    required_keys: set[str] = set()
    required_count = 0
    for raw in required_capabilities:
        required_count += 1
        if required_count > MAX_REQUIRED_CAPABILITIES:
            raise ValueError("Too many required capabilities")
        key = _normalize_name(raw, "Required capability")
        if key not in required_keys:
            required.append(raw.strip())
            required_keys.add(key)

    available: list[str] = []
    available_keys: set[str] = set()
    catalog_count = 0
    for entry in tool_catalog:
        catalog_count += 1
        if catalog_count > MAX_TOOL_CATALOG_ENTRIES:
            raise ValueError("Tool catalog exceeds the supported limit")
        if not isinstance(entry, Mapping):
            raise TypeError("Tool catalog entries must be mappings")
        key = _normalize_name(entry.get("name"), "Registered tool name")
        if key not in available_keys:
            available.append(str(entry["name"]).strip())
            available_keys.add(key)

    matched = required_keys & available_keys
    # Preserve the user's requirement order in all report sections.
    available_required = tuple(
        name for name in required if _normalize_name(name, "Required capability") in matched
    )
    missing = tuple(
        name
        for name in required
        if _normalize_name(name, "Required capability") not in available_keys
    )
    return CapabilityGapReport(
        required=tuple(required),
        available=available_required,
        missing=missing,
    )
