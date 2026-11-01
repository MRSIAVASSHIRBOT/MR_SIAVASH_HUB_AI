from __future__ import annotations

from fastapi.testclient import TestClient

from client_helpers import authenticated_client
from mrhub.config import get_settings
from mrhub.main import create_app


def test_capability_candidate_registration_and_list_are_authenticated(tmp_path, monkeypatch):
    monkeypatch.setenv("MRH_DATABASE_PATH", str(tmp_path / "capability-api.sqlite3"))
    get_settings.cache_clear()
    try:
        client = authenticated_client()
        created = client.post(
            "/capabilities/candidates",
            json={
                "source_url": "https://github.com/example/video-tool",
                "display_name": "Video Tool",
                "summary": "Candidate source for video workflows.",
                "capabilities": ["video.generate", "video.inspect"],
            },
        )
        assert created.status_code == 201
        candidate = created.json()
        assert candidate["status"] == "discovered"
        assert candidate["canonical_url"] == "https://github.com/example/video-tool"
        assert candidate["capabilities"] == ["video.generate", "video.inspect"]

        listed = client.get("/capabilities/candidates?status=discovered")
        assert listed.status_code == 200
        assert listed.json()["count"] == 1
        assert listed.json()["items"][0]["candidate_id"] == candidate["candidate_id"]
    finally:
        get_settings.cache_clear()


def test_capability_candidate_registration_rejects_non_https_source(tmp_path, monkeypatch):
    monkeypatch.setenv("MRH_DATABASE_PATH", str(tmp_path / "capability-url-api.sqlite3"))
    get_settings.cache_clear()
    try:
        client = authenticated_client()
        response = client.post(
            "/capabilities/candidates",
            json={"source_url": "http://example.com/tool", "display_name": "Unsafe URL"},
        )
        assert response.status_code == 422
        assert client.get("/capabilities/candidates").json()["count"] == 0
    finally:
        get_settings.cache_clear()


def test_capability_approval_requires_review_evidence(tmp_path, monkeypatch):
    monkeypatch.setenv("MRH_DATABASE_PATH", str(tmp_path / "capability-approval-api.sqlite3"))
    get_settings.cache_clear()
    try:
        client = authenticated_client()
        created = client.post(
            "/capabilities/candidates",
            json={"source_url": "https://github.com/example/tool", "display_name": "Tool"},
        )
        candidate_id = created.json()["candidate_id"]
        reviewing = client.post(
            f"/capabilities/candidates/{candidate_id}/transition",
            json={"status": "reviewing"},
        )
        assert reviewing.status_code == 200

        blocked = client.post(
            f"/capabilities/candidates/{candidate_id}/transition",
            json={"status": "approved", "license_id": "MIT"},
        )
        assert blocked.status_code == 409
        assert "known license" in blocked.json()["detail"]
    finally:
        get_settings.cache_clear()


def test_capability_catalog_requires_authentication(tmp_path, monkeypatch):
    monkeypatch.setenv("MRH_DATABASE_PATH", str(tmp_path / "capability-auth-api.sqlite3"))
    get_settings.cache_clear()
    try:
        response = TestClient(create_app()).get("/capabilities/candidates")
        assert response.status_code in (401, 403)
    finally:
        get_settings.cache_clear()
