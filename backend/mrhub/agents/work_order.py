"""Structured task work-order contract for Goal-to-Prompt Intelligence (GPI).

This model validates a proposed work order; it does not authorize tools or actions.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    computed_field,
    field_validator,
    model_validator,
)

from mrhub.agents.capability_gaps import (
    MAX_NAME_LENGTH as MAX_REGISTERED_TOOL_NAME_LENGTH,
)
from mrhub.agents.capability_gaps import (
    CapabilityGapReport,
    evaluate_capability_gaps,
)
from mrhub.domain.tasks import RiskClass

MAX_WORK_ORDER_ITEM_LENGTH = 300
MAX_WORK_ORDER_DEPENDENCY_LENGTH = 200

WorkOrderText = Annotated[
    str, Field(min_length=1, max_length=MAX_WORK_ORDER_ITEM_LENGTH)
]
WorkOrderDependency = Annotated[
    str, Field(min_length=1, max_length=MAX_WORK_ORDER_DEPENDENCY_LENGTH)
]
WorkOrderCapability = Annotated[
    str, Field(min_length=1, max_length=MAX_REGISTERED_TOOL_NAME_LENGTH)
]
WorkOrderComplexity = Literal["low", "moderate", "high"]


class WorkOrder(BaseModel):
    """A bounded, reviewable task specification produced from a natural-language goal."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    goal: str = Field(min_length=1, max_length=1_000)
    intent: str = Field(min_length=1, max_length=500)
    scope: str = Field(default="", max_length=1_000)
    assumptions: list[WorkOrderText] = Field(default_factory=list, max_length=12)
    constraints: list[WorkOrderText] = Field(default_factory=list, max_length=20)
    dependencies: list[WorkOrderDependency] = Field(default_factory=list, max_length=20)
    required_capabilities: list[WorkOrderCapability] = Field(default_factory=list, max_length=20)
    estimated_complexity: WorkOrderComplexity = "moderate"
    missing_information: list[WorkOrderText] = Field(default_factory=list, max_length=12)
    clarification_questions: list[WorkOrderText] = Field(default_factory=list, max_length=12)
    research_required: bool = Field(default=False, strict=True)
    research_questions: list[WorkOrderText] = Field(default_factory=list, max_length=8)
    acceptance_criteria: list[WorkOrderText] = Field(min_length=1, max_length=12)
    verification_steps: list[WorkOrderText] = Field(min_length=1, max_length=12)
    risk_class: RiskClass

    @field_validator("scope")
    @classmethod
    def normalize_scope(cls, value: str) -> str:
        """Normalize optional scope text before risk analysis and serialization."""
        return value.strip()

    @field_validator("goal", "intent")
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("value must not be blank")
        return normalized

    @field_validator(
        "assumptions", "constraints", "dependencies", "required_capabilities",
        "missing_information", "clarification_questions", "research_questions",
        "acceptance_criteria", "verification_steps",
    )
    @classmethod
    def normalize_nonblank_items(cls, items: list[str]) -> list[str]:
        normalized = [item.strip() for item in items]
        if any(not item for item in normalized):
            raise ValueError("list entries must not be blank")
        return normalized


    @model_validator(mode="after")
    def validate_clarification_and_research(self) -> "WorkOrder":
        """Require actionable questions whenever information or research is missing."""
        if self.missing_information and not self.clarification_questions:
            raise ValueError("Missing information must include at least one clarification question")
        if self.research_required and not self.research_questions:
            raise ValueError("Research-required work orders must include research questions")
        if not self.research_required and self.research_questions:
            raise ValueError("Research questions require research_required=true")
        return self

    @computed_field
    @property
    def needs_clarification(self) -> bool:
        """Whether the goal needs additional user input before reliable planning."""
        return bool(self.missing_information or self.clarification_questions)

    @computed_field
    @property
    def tool_use_required(self) -> bool:
        """Derive tool need from validated capability requirements, not model prose."""
        return bool(self.required_capabilities)

    @computed_field
    @property
    def planning_readiness(
        self,
    ) -> Literal["needs_clarification", "needs_research", "ready_for_review"]:
        """Readiness for review; never means execution is authorized."""
        if self.needs_clarification:
            return "needs_clarification"
        if self.research_required:
            return "needs_research"
        return "ready_for_review"


# Backwards-compatible public name retained for existing route and client imports.
WorkOrderCapabilityAssessment = CapabilityGapReport


def assess_work_order_capabilities(
    work_order: WorkOrder,
    registered_tools: Iterable[Mapping[str, object]],
) -> WorkOrderCapabilityAssessment:
    """Delegate WorkOrder presence checks to the shared CGI evaluator.

    WorkOrder itself caps required_capabilities at 20; the shared evaluator
    retains its broader 50-item ceiling for other API consumers.
    """
    return evaluate_capability_gaps(work_order.required_capabilities, registered_tools)
