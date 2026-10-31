"""Deterministic policy checks for agent and tool actions."""

from enum import StrEnum
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field

from mrhub.domain.tasks import RiskClass


class PolicyDecision(StrEnum):
    ALLOW = "allow"
    REQUIRE_APPROVAL = "require_approval"
    DENY = "deny"


class ActionRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    action: str = Field(min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9_.:-]+$")
    risk_class: RiskClass
    granted_permissions: frozenset[str] = frozenset()
    required_permissions: frozenset[str] = frozenset()
    external_side_effect: bool = False
    user_approved: bool = False


class PolicyResult(BaseModel):
    decision: PolicyDecision
    reason: str


class PolicyEngine:
    """Small explicit policy engine. Unknown permissions are never inferred."""

    LOW_RISK_TASK_TYPES: ClassVar[frozenset[str]] = frozenset({
        "demo.echo",
        "analysis.summarize",
        "content.draft",
        "memory.search",
    })

    def classify_task_type(self, task_type: str) -> RiskClass:
        """Classify task types server-side; unknown types require approval."""
        if task_type in self.LOW_RISK_TASK_TYPES:
            return RiskClass.LOW
        return RiskClass.HIGH

    def evaluate(self, request: ActionRequest) -> PolicyResult:
        if request.risk_class is RiskClass.PROHIBITED:
            return PolicyResult(decision=PolicyDecision.DENY, reason="Prohibited risk class")

        missing = request.required_permissions - request.granted_permissions
        if missing:
            return PolicyResult(
                decision=PolicyDecision.DENY,
                reason="Missing required permission grants: " + ", ".join(sorted(missing)),
            )

        needs_approval = (
            request.risk_class is RiskClass.HIGH or request.external_side_effect
        )
        if needs_approval and not request.user_approved:
            return PolicyResult(
                decision=PolicyDecision.REQUIRE_APPROVAL,
                reason="High-impact or external action requires explicit approval",
            )

        return PolicyResult(decision=PolicyDecision.ALLOW, reason="Policy checks passed")
