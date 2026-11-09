import pytest

from mrhub.agents.proposal_evaluation import evaluate_agent_proposal
from mrhub.agents.proposals import AgentProposal
from mrhub.agents.registry import build_default_agent_registry
from mrhub.tools.builtins import build_tool_registry


def make_proposal(**overrides):
    values = {
        "name": "research_assistant",
        "description": "Summarize supplied research evidence.",
        "instructions": "Use only supplied evidence and cite source references.",
        "allowed_tools": ["text.echo"],
        "max_turns": 2,
        "rationale": "A bounded specialist for reviewed research workflows.",
    }
    values.update(overrides)
    return AgentProposal.model_validate(values)


def test_preflight_passes_without_registering_or_executing_candidate():
    tools = build_tool_registry()
    agents = build_default_agent_registry(tools)
    before = agents.catalog()

    report = evaluate_agent_proposal(make_proposal(), agents=agents, tools=tools)

    assert report["status"] == "passed"
    assert report["recommendation"] == "eligible_for_owner_review"
    assert report["execution_performed"] is False
    assert report["activation_performed"] is False
    assert report["permission_granted"] is False
    assert all(check["status"] == "passed" for check in report["checks"])
    assert agents.catalog() == before
    with pytest.raises(LookupError):
        agents.get("research_assistant")


def test_preflight_blocks_existing_agent_name():
    tools = build_tool_registry()
    agents = build_default_agent_registry(tools)

    report = evaluate_agent_proposal(
        make_proposal(name="aria_architect"),
        agents=agents,
        tools=tools,
    )

    assert report["status"] == "blocked"
    assert report["recommendation"] == "revise_proposal"
    assert next(check for check in report["checks"] if check["id"] == "name_available")[
        "status"
    ] == "failed"


def test_preflight_blocks_unknown_tools_without_invoking_them():
    tools = build_tool_registry()
    agents = build_default_agent_registry(tools)

    report = evaluate_agent_proposal(
        make_proposal(allowed_tools=["unknown.tool"]),
        agents=agents,
        tools=tools,
    )

    assert report["status"] == "blocked"
    check = next(item for item in report["checks"] if item["id"] == "tools_registered")
    assert check["status"] == "failed"
    assert "unknown.tool" in check["detail"]
    assert report["execution_performed"] is False


def test_preflight_reports_duplicate_tool_identifiers():
    tools = build_tool_registry()
    agents = build_default_agent_registry(tools)

    report = evaluate_agent_proposal(
        make_proposal(allowed_tools=["text.echo", "text.echo"]),
        agents=agents,
        tools=tools,
    )

    assert report["status"] == "blocked"
    assert next(check for check in report["checks"] if check["id"] == "tool_scope_unique")[
        "status"
    ] == "failed"


def test_preflight_api_is_owner_scoped_and_does_not_change_proposal_state():
    from client_helpers import authenticated_client

    client = authenticated_client()
    payload = {
        "name": "preflight_researcher",
        "description": "Summarize supplied research evidence.",
        "instructions": "Use only supplied evidence and cite source references.",
        "allowed_tools": ["text.echo"],
        "max_turns": 2,
        "rationale": "A bounded specialist for reviewed research workflows.",
    }
    created = client.post("/agent/proposals", json=payload)
    assert created.status_code == 201
    record = created.json()

    response = client.get(f"/agent/proposals/{record['proposal_id']}/evaluation")

    assert response.status_code == 200
    report = response.json()
    assert report["status"] == "passed"
    assert report["proposal_status"] == "pending"
    assert report["execution_performed"] is False
    assert report["activation_performed"] is False
    assert report["permission_granted"] is False

    unchanged = client.get(f"/agent/proposals/{record['proposal_id']}")
    assert unchanged.status_code == 200
    assert unchanged.json()["status"] == "pending"
    assert unchanged.json()["activation_state"] == "inactive"


def test_preflight_api_requires_authentication():
    from client_helpers import authenticated_client

    owner_client = authenticated_client()
    payload = {
        "name": "private_preflight_researcher",
        "description": "Summarize supplied research evidence.",
        "instructions": "Use only supplied evidence and cite source references.",
        "allowed_tools": [],
        "max_turns": 1,
        "rationale": "A private owner-scoped candidate.",
    }
    created = owner_client.post("/agent/proposals", json=payload)
    assert created.status_code == 201

    response = owner_client.get(
        f"/agent/proposals/{created.json()['proposal_id']}/evaluation",
        headers={"Authorization": "Bearer invalid-owner-token"},
    )
    assert response.status_code in (401, 403)
