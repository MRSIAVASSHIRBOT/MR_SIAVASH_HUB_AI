"""Review-only validation for proposed specialist agent profiles.

A valid proposal is a candidate definition, not an active agent or permission grant.
Activation must remain a separate owner-reviewed operation.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from mrhub.agents.registry import AgentProfile, AgentRegistry
from mrhub.tools.registry import ToolRegistry


class AgentProposal(BaseModel):
    """Strict, bounded description of a candidate specialist."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=64)
    description: str = Field(min_length=1, max_length=200)
    instructions: str = Field(min_length=1, max_length=1_200)
    allowed_tools: list[Annotated[str, Field(min_length=1, max_length=80)]] = Field(
        default_factory=list, max_length=10
    )
    max_turns: int = Field(default=2, ge=1, le=3)
    rationale: str = Field(min_length=1, max_length=1_000)


def validate_agent_proposal(
    proposal: AgentProposal,
    *,
    agents: AgentRegistry,
    tools: ToolRegistry,
) -> AgentProfile:
    """Validate a candidate against current registries without activating it.

    This function deliberately has no persistence, registration, permission-grant,
    or execution side effects. The caller must obtain owner review before activation.
    """
    try:
        agents.get(proposal.name)
    except LookupError:
        pass
    else:
        raise ValueError("Agent name is already registered")

    if len(set(proposal.allowed_tools)) != len(proposal.allowed_tools):
        raise ValueError("Agent proposal contains duplicate tool names")

    profile = AgentProfile(
        name=proposal.name,
        description=proposal.description,
        instructions=proposal.instructions,
        allowed_tools=frozenset(proposal.allowed_tools),
        max_turns=proposal.max_turns,
    )

    # Reuse the canonical registry's naming, length, and bounded-turn validation
    # without mutating the live registry.
    candidate_registry = AgentRegistry()
    candidate_registry.register(profile)

    # Every requested tool must already exist. This does not grant permission:
    # ToolRegistry.invoke still applies its independent policy on every call.
    for tool_name in sorted(profile.allowed_tools):
        tools.get(tool_name)

    return profile
