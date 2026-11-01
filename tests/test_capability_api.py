from __future__ import annotations

from fastapi.testclient import TestClient

from client_helpers import authenticated_client
from mrhub.config import get_settings
from mrhub.main import create_app
from mrhub.capabilities.github_discovery import GitHubDiscoveryError


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


def test_github_discovery_endpoint_returns_metadata_and_registers_review_candidate(monkeypatch):
    from mrhub.api.routes import capabilities as capabilities_route

    fake_result = {
        "full_name": "Example/VideoTool",
        "html_url": "https://github.com/Example/VideoTool",
        "license_spdx_id": "MIT",
        "candidate": {"candidate_id": "candidate-1", "status": "discovered"},
        "source_code_fetched": False,
        "source_code_executed": False,
        "installation_started": False,
        "approval_granted": False,
    }

    def fake_discovery(source_url, registry):
        assert source_url == "https://github.com/Example/VideoTool"
        return object(), fake_result

    monkeypatch.setattr(capabilities_route, "discover_github_candidate", fake_discovery)
    client = authenticated_client()
    response = client.post(
        "/capabilities/discover",
        json={"source_url": "https://github.com/Example/VideoTool"},
    )

    assert response.status_code == 201
    assert response.json()["candidate"]["status"] == "discovered"
    assert response.json()["source_code_executed"] is False
    assert response.json()["approval_granted"] is False


def test_github_discovery_endpoint_surfaces_safe_not_found_error(monkeypatch):
    from mrhub.api.routes import capabilities as capabilities_route

    def missing_repository(_source_url, _registry):
        raise GitHubDiscoveryError(
            "repository_not_found", "Public repository not found", status_code=404
        )

    monkeypatch.setattr(capabilities_route, "discover_github_candidate", missing_repository)
    client = authenticated_client()
    response = client.post(
        "/capabilities/discover",
        json={"source_url": "https://github.com/Example/Missing"},
    )

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "repository_not_found"
