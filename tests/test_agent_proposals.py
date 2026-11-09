import pytest
from pydantic import ValidationError

from mrhub.agents.proposals import AgentProposal, validate_agent_proposal
from mrhub.agents.registry import build_default_agent_registry
from mrhub.tools.builtins import build_tool_registry


def make_proposal(**overrides):
    values = {
        "name": "research_assistant",
        "description": "Summarize supplied research evidence.",
        "instructions": "Use only supplied evidence and cite source references.",
        "allowed_tools": [],
        "max_turns": 2,
        "rationale": "Provides a bounded research specialist for reviewed workflows.",
    }
    values.update(overrides)
    return AgentProposal.model_validate(values)


def test_valid_proposal_returns_candidate_without_registering_it():
    tools = build_tool_registry()
    agents = build_default_agent_registry(tools)
    before = agents.catalog()

    candidate = validate_agent_proposal(
        make_proposal(allowed_tools=["text.echo"]),
        agents=agents,
        tools=tools,
    )

    assert candidate.name == "research_assistant"
    assert candidate.allowed_tools == frozenset({"text.echo"})
    assert candidate.max_turns == 2
    assert agents.catalog() == before
    with pytest.raises(LookupError):
        agents.get("research_assistant")


def test_proposal_rejects_an_already_registered_agent_name():
    tools = build_tool_registry()
    agents = build_default_agent_registry(tools)

    with pytest.raises(ValueError, match="already registered"):
        validate_agent_proposal(
            make_proposal(name="aria_architect"),
            agents=agents,
            tools=tools,
        )


def test_proposal_rejects_unknown_tools_without_changing_registry():
    tools = build_tool_registry()
    agents = build_default_agent_registry(tools)
    before = agents.catalog()

    with pytest.raises(LookupError, match="not registered"):
        validate_agent_proposal(
            make_proposal(allowed_tools=["untrusted.dynamic_tool"]),
            agents=agents,
            tools=tools,
        )

    assert agents.catalog() == before


def test_proposal_rejects_duplicate_tool_names():
    tools = build_tool_registry()
    agents = build_default_agent_registry(tools)

    with pytest.raises(ValueError, match="duplicate tool"):
        validate_agent_proposal(
            make_proposal(allowed_tools=["text.echo", "text.echo"]),
            agents=agents,
            tools=tools,
        )


@pytest.mark.parametrize("max_turns", [0, 4])
def test_proposal_rejects_unbounded_turn_limits(max_turns):
    with pytest.raises(ValidationError):
        make_proposal(max_turns=max_turns)


def test_proposal_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        make_proposal(unreviewed_permission="admin")


def test_proposal_rejects_empty_or_oversized_tool_identifiers():
    with pytest.raises(ValidationError):
        make_proposal(allowed_tools=[""])
    with pytest.raises(ValidationError):
        make_proposal(allowed_tools=["x" * 81])
