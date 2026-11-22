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
    risk_class: RiskClass = RiskClass.MODERATE

    @field_validator(
        "assumptions", "constraints", "dependencies", "required_capabilities",
        "acceptance_criteria", "verification_steps",
    )
    @classmethod
    def validate_nonblank_items(cls, items: list[str]) -> list[str]:
        if any(not item.strip() for item in items):
            raise ValueError("list entries must not be blank")
        return items
