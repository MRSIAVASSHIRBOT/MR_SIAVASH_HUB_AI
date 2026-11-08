from fastapi.testclient import TestClient

from mrhub.config import get_settings
from mrhub.main import create_app


def test_project_registry_requires_authenticated_owner(tmp_path, monkeypatch):
    monkeypatch.setenv("MRH_DATABASE_PATH", str(tmp_path / "projects.sqlite3"))
    get_settings.cache_clear()
    client = TestClient(create_app())

    response = client.get("/projects/registry")

    assert response.status_code == 401


def test_project_registry_lists_only_explicit_active_projects(tmp_path, monkeypatch):
    monkeypatch.setenv("MRH_DATABASE_PATH", str(tmp_path / "projects.sqlite3"))
    get_settings.cache_clear()
    client = TestClient(create_app())

    setup = client.post("/auth/setup", json={"password": "test-only-strong-password-2026"})
    assert setup.status_code == 201
    login = client.post(
        "/auth/login",
        json={"username": "owner", "password": "test-only-strong-password-2026"},
    )
    assert login.status_code == 200
    client.headers.update({"Authorization": f"Bearer {login.json()['access_token']}"})

    response = client.get("/projects/registry")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    payload = response.json()
    assert payload["contract_version"] == "1.0"
    assert payload["source"] == "explicit_project_registry"
    assert len(payload["observed_at"]) > 10
    assert [project["project_id"] for project in payload["projects"]] == [
        "mr-siavash-hub-ai",
        "mr-siavash-ai",
        "gshop",
    ]
    assert all(project["repository_status"] == "not_configured" for project in payload["projects"])
    assert all(project["runtime_status"] == "unknown" for project in payload["projects"])
    assert all(
        project["infrastructure_status"] == "not_configured"
        for project in payload["projects"]
    )
    assert payload["projects"][1]["service_url"] == "https://mrsiavasshirbot.github.io/MR_SIAVASH_AI/"
    assert payload["projects"][2]["service_url"] == "https://gshop11.ir/"
    for project in payload["projects"]:
        observations = project["status_observations"]
        assert set(observations) == {"repository", "runtime", "infrastructure"}
        expected = {
            "repository": ("not_configured", "github_integration_not_configured"),
            "runtime": ("unknown", "runtime_probe_not_configured"),
            "infrastructure": ("not_configured", "cloudflare_integration_not_configured"),
        }
        for dimension, (status, reason_code) in expected.items():
            observation = observations[dimension]
            assert observation["status"] == status
            assert observation["source"] == "project_registry_configuration"
            assert observation["observed_at"] == payload["observed_at"]
            assert observation["reason_code"] == reason_code


def test_project_registry_does_not_claim_unverified_health(tmp_path, monkeypatch):
    monkeypatch.setenv("MRH_DATABASE_PATH", str(tmp_path / "projects.sqlite3"))
    get_settings.cache_clear()
    client = TestClient(create_app())
    client.post("/auth/setup", json={"password": "test-only-strong-password-2026"})
    login = client.post(
        "/auth/login",
        json={"username": "owner", "password": "test-only-strong-password-2026"},
    )
    client.headers.update({"Authorization": f"Bearer {login.json()['access_token']}"})

    projects = client.get("/projects/registry").json()["projects"]

    assert not any(project["runtime_status"] == "healthy" for project in projects)
    assert not any(project["repository_status"] == "healthy" for project in projects)
