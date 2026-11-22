"""Structured task work-order contract for Goal-to-Prompt Intelligence (GPI).

This model validates a proposed work order; it does not authorize tools or actions.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

from mrhub.domain.tasks import RiskClass


class WorkOrder(BaseModel):
    """A bounded, reviewable task specification produced from a natural-language goal."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    goal: str = Field(min_length=1, max_length=1_000)
    intent: str = Field(min_length=1, max_length=500)
    scope: str = Field(default="", max_length=1_000)
    assumptions: list[str] = Field(default_factory=list, max_length=12)
    constraints: list[str] = Field(default_factory=list, max_length=20)
    dependencies: list[str] = Field(default_factory=list, max_length=20)
    required_capabilities: list[str] = Field(default_factory=list, max_length=20)
    acceptance_criteria: list[str] = Field(min_length=1, max_length=12)
    verification_steps: list[str] = Field(min_length=1, max_length=12)
    risk_class: RiskClass

    @field_validator(
        "assumptions", "constraints", "dependencies", "required_capabilities",
        "acceptance_criteria", "verification_steps",
    )
    @classmethod
    def validate_nonblank_items(cls, items: list[str]) -> list[str]:
        if any(not item.strip() for item in items):
            raise ValueError("list entries must not be blank")
        return items



from collections.abc import Iterable, Mapping
from dataclasses import dataclass


MAX_REGISTERED_TOOL_COUNT = 200
MAX_REGISTERED_TOOL_NAME_LENGTH = 80


@dataclass(frozen=True)
class WorkOrderCapabilityAssessment:
    """Read-only capability presence report; it is not an authorization decision."""

    required: tuple[str, ...]
    available: tuple[str, ...]
    missing: tuple[str, ...]

    @property
    def complete(self) -> bool:
        return not self.missing


def assess_work_order_capabilities(
    work_order: WorkOrder,
    registered_tools: Iterable[Mapping[str, object]],
) -> WorkOrderCapabilityAssessment:
    """Compare required capability identifiers with registered tool names.

    Exact case-insensitive name matching prevents descriptive metadata from
    being mistaken for an executable capability. No tool is invoked.
    """
    available_names: set[str] = set()
    count = 0
    for entry in registered_tools:
        count += 1
        if count > MAX_REGISTERED_TOOL_COUNT:
            raise ValueError("Registered tool catalog exceeds the supported limit")
        if not isinstance(entry, Mapping):
            raise TypeError("Registered tool entries must be mappings")
        raw_name = entry.get("name")
        if not isinstance(raw_name, str):
            raise TypeError("Registered tool name must be a string")
        name = raw_name.strip()
        if not name or len(name) > MAX_REGISTERED_TOOL_NAME_LENGTH:
            raise ValueError("Registered tool name is outside the supported bounds")
        available_names.add(name.casefold())

    required: list[str] = []
    available: list[str] = []
    missing: list[str] = []
    seen: set[str] = set()
    for raw_name in work_order.required_capabilities:
        name = raw_name.strip()
        key = name.casefold()
        if key in seen:
            continue
        seen.add(key)
        required.append(name)
        if key in available_names:
            available.append(name)
        else:
            missing.append(name)

    return WorkOrderCapabilityAssessment(
        required=tuple(required),
        available=tuple(available),
        missing=tuple(missing),
    )
