"""Deterministic, read-only preflight evaluation for agent proposals."""

from __future__ import annotations

from mrhub.agents.proposals import AgentProposal
from mrhub.agents.registry import AgentProfile, AgentRegistry
from mrhub.tools.registry import ToolRegistry


def evaluate_agent_proposal(
    proposal: AgentProposal,
    *,
    agents: AgentRegistry,
    tools: ToolRegistry,
) -> dict[str, object]:
    """Return a static readiness report without executing or registering anything."""
    checks: list[dict[str, str]] = []

    def record(check_id: str, passed: bool, detail: str) -> None:
        checks.append({
            "id": check_id,
            "status": "passed" if passed else "failed",
            "detail": detail,
        })

    profile = AgentProfile(
        name=proposal.name,
        description=proposal.description,
        instructions=proposal.instructions,
        allowed_tools=frozenset(proposal.allowed_tools),
        max_turns=proposal.max_turns,
    )

    candidate_registry = AgentRegistry()
    try:
        candidate_registry.register(profile)
    except ValueError:
        record("profile_constraints", False, "Profile violates the registered agent constraints")
    else:
        record("profile_constraints", True, "Name and profile bounds satisfy registry constraints")

    try:
        agents.get(proposal.name)
    except LookupError:
        record("name_available", True, "No built-in agent currently uses this name")
    else:
        record("name_available", False, "An existing agent already uses this name")

    unique_tools = len(set(proposal.allowed_tools)) == len(proposal.allowed_tools)
    record(
        "tool_scope_unique",
        unique_tools,
        "Requested tool identifiers are unique"
        if unique_tools else "Requested tool identifiers contain duplicates",
    )

    bounded_tool_count = len(proposal.allowed_tools) <= 10
    record(
        "tool_count_bounded",
        bounded_tool_count,
        "Requested tool count is within the limit"
        if bounded_tool_count else "Requested tool count exceeds the limit",
    )

    unknown_tools: list[str] = []
    for tool_name in sorted(set(proposal.allowed_tools)):
        try:
            tools.get(tool_name)
        except LookupError:
            unknown_tools.append(tool_name)
    record(
        "tools_registered",
        not unknown_tools,
        "Every requested tool exists in the server registry"
        if not unknown_tools else "Unknown tools: " + ", ".join(unknown_tools),
    )

    bounded_turns = 1 <= proposal.max_turns <= 3
    record(
        "turn_budget_bounded",
        bounded_turns,
        "Maximum turn count is within the limit"
        if bounded_turns else "Maximum turn count is outside the supported range",
    )

    passed = all(check["status"] == "passed" for check in checks)
    return {
        "status": "passed" if passed else "blocked",
        "recommendation": "eligible_for_owner_review" if passed else "revise_proposal",
        "checks": checks,
        "execution_performed": False,
        "activation_performed": False,
        "permission_granted": False,
    }
