from fastapi.testclient import TestClient

from client_helpers import authenticated_client
from mrhub.config import get_settings
from mrhub.main import create_app


def test_research_opportunity_evidence_and_assessment_lifecycle(tmp_path, monkeypatch):
    monkeypatch.setenv("MRH_DATABASE_PATH", str(tmp_path / "research.sqlite3"))
    get_settings.cache_clear()
    try:
        client = authenticated_client()
        created = client.post("/research/opportunities", json={
            "domain_id": "web",
            "title": "Affordable website setup",
            "problem_statement": "Small local businesses struggle to launch and maintain a website.",
            "audience": "Small local businesses",
            "solution_hypothesis": "A guided website builder with managed maintenance.",
        })
        assert created.status_code == 201
        opportunity = created.json()
        assert opportunity["status"] == "new"
        assert opportunity["priority_score"] is None
        opportunity_id = opportunity["opportunity_id"]

        evidence = client.post(f"/research/opportunities/{opportunity_id}/evidence", json={
            "source_type": "public_discussion",
            "source_url": "https://example.com/community/thread-1",
            "source_label": "Public community thread",
            "observation_summary": "Several participants describe website setup as confusing and expensive.",
            "signal_strength": "high",
        })
        assert evidence.status_code == 201
        assert evidence.json()["canonical_url"] == "https://example.com/community/thread-1"

        assessed = client.patch(f"/research/opportunities/{opportunity_id}", json={
            "status": "validating", "impact_score": 5, "frequency_score": 4, "feasibility_score": 3,
        })
        assert assessed.status_code == 200
        assert assessed.json()["priority_score"] == 82
        assert len(assessed.json()["evidence"]) == 1

        listed = client.get("/research/opportunities?domain_id=web")
        assert listed.status_code == 200
        assert listed.json()["count"] == 1
    finally:
        get_settings.cache_clear()


def test_research_rejects_unsafe_urls_duplicate_evidence_and_invalid_transition(tmp_path, monkeypatch):
    monkeypatch.setenv("MRH_DATABASE_PATH", str(tmp_path / "research-validation.sqlite3"))
    get_settings.cache_clear()
    try:
        client = authenticated_client()
        created = client.post("/research/opportunities", json={
            "domain_id": "content", "title": "Content planning",
            "problem_statement": "People struggle to plan consistent content.", "audience": "Creators",
        })
        opportunity_id = created.json()["opportunity_id"]
        payload = {
            "source_type": "app_review", "source_url": "http://127.0.0.1/private",
            "source_label": "Unsafe source", "observation_summary": "Not accepted.",
        }
        assert client.post(f"/research/opportunities/{opportunity_id}/evidence", json=payload).status_code == 422
        payload["source_url"] = "https://example.com/review/1"
        assert client.post(f"/research/opportunities/{opportunity_id}/evidence", json=payload).status_code == 201
        assert client.post(f"/research/opportunities/{opportunity_id}/evidence", json=payload).status_code == 409
        invalid = client.patch(f"/research/opportunities/{opportunity_id}", json={"status": "validated"})
        assert invalid.status_code == 409
    finally:
        get_settings.cache_clear()


def test_platform_and_research_routes_require_authentication(tmp_path, monkeypatch):
    monkeypatch.setenv("MRH_DATABASE_PATH", str(tmp_path / "research-auth.sqlite3"))
    get_settings.cache_clear()
    try:
        client = TestClient(create_app())
        assert client.get("/platform/domains").status_code in (401, 403)
        assert client.get("/research/opportunities").status_code in (401, 403)
    finally:
        get_settings.cache_clear()
