"""Deterministic CGI capability-gap evaluation against registered tools.

This evaluator reports gaps only. It does not discover, install, grant, or execute
capabilities; descriptions are not treated as executable capability identifiers.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from mrhub.tools.registry import ToolRegistry


MAX_REQUIRED_CAPABILITIES = 50
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
    for raw in required_capabilities:
        key = _normalize_name(raw, "Required capability")
        if key not in required_keys:
            required.append(raw.strip())
            required_keys.add(key)
        if len(required) > MAX_REQUIRED_CAPABILITIES:
            raise ValueError("Too many required capabilities")

    available_keys: set[str] = set()
    for entry in tool_catalog:
        if not isinstance(entry, Mapping):
            raise TypeError("Tool catalog entries must be mappings")
        key = _normalize_name(entry.get("name"), "Registered tool name")
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


def evaluate_registered_tool_gaps(
    required_capabilities: Iterable[str],
    tool_registry: ToolRegistry,
) -> CapabilityGapReport:
    """Evaluate requirements against the live, server-owned ToolRegistry catalog.

    Only registered tool names are considered. Descriptions and schemas remain
    metadata, and this function never invokes a handler or changes permissions.
    """
    return evaluate_capability_gaps(required_capabilities, tool_registry.catalog())
