import secrets
import sqlite3
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from client_helpers import authenticated_client
from mrhub.agents.proposal_repository import AgentProposalRepository
from mrhub.config import get_settings
from mrhub.infrastructure.database import TaskRepository
from mrhub.main import create_app
from mrhub.security.auth import _password_digest


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

    repeated_review = client.post(
        f"/agent/proposals/{record['proposal_id']}/review",
        json={"fingerprint": record["fingerprint"], "decision": "approved"},
    )
    assert repeated_review.status_code == 409
    assert repeated_review.json()["detail"] == "Proposal was already reviewed or changed"


def test_agent_proposal_rejection_is_terminal_and_never_activates():
    client = authenticated_client()
    created = client.post("/agent/proposals", json=proposal_payload())
    assert created.status_code == 201
    record = created.json()

    rejected = client.post(
        f"/agent/proposals/{record['proposal_id']}/review",
        json={"fingerprint": record["fingerprint"], "decision": "rejected"},
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"
    assert rejected.json()["activation_state"] == "inactive"

    repeated_review = client.post(
        f"/agent/proposals/{record['proposal_id']}/review",
        json={"fingerprint": record["fingerprint"], "decision": "approved"},
    )
    assert repeated_review.status_code == 409
    assert client.get(f"/agent/proposals/{record['proposal_id']}").json()["status"] == "rejected"


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


def test_agent_proposal_api_isolates_records_between_authenticated_owners():
    owner_client = authenticated_client()
    created = owner_client.post("/agent/proposals", json=proposal_payload())
    assert created.status_code == 201
    record = created.json()

    # Create a second legitimate account in the same test database. The
    # production bootstrap remains single-owner; this exercises the schema's
    # owner boundary as soon as additional accounts exist.
    password = "second-owner-test-password-2026"
    salt = secrets.token_bytes(16)
    TaskRepository(get_settings().database_path).create_auth_user(
        "second-owner",
        "second-owner",
        salt.hex(),
        _password_digest(password, salt).hex(),
    )
    login = owner_client.post(
        "/auth/login",
        json={"username": "second-owner", "password": password},
    )
    assert login.status_code == 200
    second_owner_headers = {
        "Authorization": f"Bearer {login.json()['access_token']}"
    }

    listed = owner_client.get("/agent/proposals", headers=second_owner_headers)
    assert listed.status_code == 200
    assert listed.json() == {"proposals": [], "count": 0}

    fetched = owner_client.get(
        f"/agent/proposals/{record['proposal_id']}",
        headers=second_owner_headers,
    )
    assert fetched.status_code == 404

    reviewed = owner_client.post(
        f"/agent/proposals/{record['proposal_id']}/review",
        headers=second_owner_headers,
        json={"fingerprint": record["fingerprint"], "decision": "approved"},
    )
    assert reviewed.status_code == 404

    owner_record = owner_client.get(
        f"/agent/proposals/{record['proposal_id']}"
    )
    assert owner_record.status_code == 200
    assert owner_record.json()["status"] == "pending"

def test_agent_proposal_rejects_duplicate_name_while_pending():
    client = authenticated_client()
    first = client.post("/agent/proposals", json=proposal_payload())
    assert first.status_code == 201
    second = client.post("/agent/proposals", json=proposal_payload())
    assert second.status_code == 422



def test_agent_proposal_lifecycle_writes_audit_events_atomically():
    client = authenticated_client()
    created = client.post("/agent/proposals", json=proposal_payload())
    assert created.status_code == 201
    record = created.json()

    reviewed = client.post(
        f"/agent/proposals/{record['proposal_id']}/review",
        json={"fingerprint": record["fingerprint"], "decision": "approved"},
    )
    assert reviewed.status_code == 200

    with sqlite3.connect(get_settings().database_path) as connection:
        events = connection.execute(
            """
            SELECT event_type, outcome, subject_type, subject_id, actor_id
            FROM audit_events
            WHERE subject_type = 'agent_proposal' AND subject_id = ?
            ORDER BY event_type
            """,
            (record["proposal_id"],),
        ).fetchall()

    assert events == [
        ("agent.proposal_created", "pending_review", "agent_proposal",
         record["proposal_id"], record["owner_user_id"]),
        ("agent.proposal_reviewed", "approved", "agent_proposal",
         record["proposal_id"], record["owner_user_id"]),
    ]



def test_agent_proposal_create_rolls_back_when_audit_write_fails(monkeypatch):
    client = authenticated_client()

    def fail_audit_write(connection, event):
        raise RuntimeError("simulated audit storage failure")

    monkeypatch.setattr(
        TaskRepository, "_insert_audit_event", staticmethod(fail_audit_write)
    )
    with pytest.raises(RuntimeError, match="simulated audit storage failure"):
        client.post("/agent/proposals", json=proposal_payload())

    with sqlite3.connect(get_settings().database_path) as connection:
        proposal_count = connection.execute(
            "SELECT COUNT(*) FROM agent_proposals"
        ).fetchone()[0]
        audit_count = connection.execute(
            "SELECT COUNT(*) FROM audit_events WHERE event_type = 'agent.proposal_created'"
        ).fetchone()[0]

    assert proposal_count == 0
    assert audit_count == 0


def test_agent_proposal_review_rolls_back_when_audit_write_fails(monkeypatch):
    client = authenticated_client()
    created = client.post("/agent/proposals", json=proposal_payload())
    assert created.status_code == 201
    record = created.json()

    def fail_audit_write(connection, event):
        raise RuntimeError("simulated audit storage failure")

    monkeypatch.setattr(
        TaskRepository, "_insert_audit_event", staticmethod(fail_audit_write)
    )
    with pytest.raises(RuntimeError, match="simulated audit storage failure"):
        client.post(
            f"/agent/proposals/{record['proposal_id']}/review",
            json={"fingerprint": record["fingerprint"], "decision": "approved"},
        )

    with sqlite3.connect(get_settings().database_path) as connection:
        status = connection.execute(
            "SELECT status FROM agent_proposals WHERE proposal_id = ?",
            (record["proposal_id"],),
        ).fetchone()[0]
        review_events = connection.execute(
            "SELECT COUNT(*) FROM audit_events WHERE event_type = 'agent.proposal_reviewed'"
        ).fetchone()[0]

    assert status == "pending"
    assert review_events == 0
