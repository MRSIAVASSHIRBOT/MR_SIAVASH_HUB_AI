from uuid import UUID

from fastapi.testclient import TestClient

from client_helpers import authenticated_client
from mrhub.agents.proposal_repository import AgentProposalRepository
from mrhub.config import get_settings
from mrhub.main import create_app


def proposal_payload(**overrides):
    payload = {
        "name": "research_assistant",
        "description": "Summarize supplied research evidence.",
        "instructions": "Use only supplied evidence and cite source references.",
        "allowed_tools": ["text.echo"],
        "max_turns": 2,
        "rationale": "A bounded specialist for owner-reviewed research tasks.",
    }
    payload.update(overrides)
    return payload


def test_agent_proposal_api_requires_authentication(tmp_path, monkeypatch):
    monkeypatch.setenv("MRH_DATABASE_PATH", str(tmp_path / "proposals.sqlite3"))
    get_settings.cache_clear()
    response = TestClient(create_app()).post("/agent/proposals", json=proposal_payload())
    assert response.status_code in (401, 403)
    get_settings.cache_clear()


def test_agent_proposal_create_list_get_and_owner_review():
    client = authenticated_client()
    created = client.post("/agent/proposals", json=proposal_payload())
    assert created.status_code == 201
    record = created.json()
    assert record["status"] == "pending"
    assert record["activation_state"] == "inactive"

    listed = client.get("/agent/proposals")
    assert listed.status_code == 200
    assert listed.json()["count"] == 1
    assert listed.json()["proposals"][0]["proposal_id"] == record["proposal_id"]

    fetched = client.get(f"/agent/proposals/{record['proposal_id']}")
    assert fetched.status_code == 200
    assert fetched.json()["fingerprint"] == record["fingerprint"]

    reviewed = client.post(
        f"/agent/proposals/{record['proposal_id']}/review",
        json={"fingerprint": record["fingerprint"], "decision": "approved"},
    )
    assert reviewed.status_code == 200
    assert reviewed.json()["status"] == "approved"
    assert reviewed.json()["activation_state"] == "inactive"
    assert reviewed.json()["reviewed_by"] == record["owner_user_id"]


def test_agent_proposal_rejects_stale_fingerprint():
    client = authenticated_client()
    created = client.post("/agent/proposals", json=proposal_payload())
    record = created.json()
    response = client.post(
        f"/agent/proposals/{record['proposal_id']}/review",
        json={"fingerprint": "0" * 64, "decision": "approved"},
    )
    assert response.status_code == 409
    assert client.get(f"/agent/proposals/{record['proposal_id']}").json()["status"] == "pending"


def test_agent_proposal_rejects_unknown_tools():
    client = authenticated_client()
    response = client.post(
        "/agent/proposals",
        json=proposal_payload(allowed_tools=["untrusted.dynamic_tool"]),
    )
    assert response.status_code == 422


def test_agent_proposal_is_owner_scoped():
    client = authenticated_client()
    created = client.post("/agent/proposals", json=proposal_payload())
    record = created.json()
    repository = AgentProposalRepository(get_settings().database_path)
    assert repository.get(
        UUID(record["proposal_id"]),
        owner_user_id="different-owner",
    ) is None


def test_agent_proposal_rejects_duplicate_name_while_pending():
    client = authenticated_client()
    first = client.post("/agent/proposals", json=proposal_payload())
    assert first.status_code == 201
    second = client.post("/agent/proposals", json=proposal_payload())
    assert second.status_code == 422
