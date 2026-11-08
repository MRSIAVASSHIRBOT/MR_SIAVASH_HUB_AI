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
    monkeypatch.setattr(
        "mrhub.projects.registry.get_repository_status",
        lambda repository: {
            "status": "healthy",
            "source": "github_public_api",
            "observed_at": "2026-11-08T12:00:00+00:00",
            "reason_code": "repository_metadata_observed",
            "repository": repository,
            "default_branch": "main",
            "latest_commit": None,
            "open_pull_requests": [],
            "open_pull_requests_sample_size": 0,
            "open_pull_requests_may_be_truncated": False,
            "latest_ci": {"status": "unknown", "source": "github_actions_public_api",
                          "observed_at": "2026-11-08T12:00:00+00:00",
                          "reason_code": "no_workflow_runs"},
        },
    )
    monkeypatch.setenv("MRH_DATABASE_PATH", str(tmp_path / "projects.sqlite3"))
    get_settings.cache_clear()
    client = TestClient(create_app())

    setup = client.post("/auth/setup", json={"password": "test-only-strong" + "-password-2026"})
    assert setup.status_code == 201
    login = client.post(
        "/auth/login",
        json={"username": "owner", "password": "test-only-strong" + "-password-2026"},
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
    assert all(project["repository_status"] == "healthy" for project in payload["projects"])
    assert all(
        project["status_observations"]["repository"]["source"] == "github_public_api"
        for project in payload["projects"]
    )
    assert all(project["repository_details"]["default_branch"] == "main" for project in payload["projects"])
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
            "repository": ("healthy", "repository_metadata_observed", "github_public_api"),
            "runtime": ("unknown", "runtime_probe_not_configured", "project_registry_configuration"),
            "infrastructure": ("not_configured", "cloudflare_integration_not_configured",
                               "project_registry_configuration"),
        }
        for dimension, (status, reason_code, source) in expected.items():
            observation = observations[dimension]
            assert observation["status"] == status
            assert observation["source"] == source
            assert observation["observed_at"] == payload["observed_at"] or dimension == "repository"
            assert observation["reason_code"] == reason_code


def test_project_registry_does_not_claim_unverified_health(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "mrhub.projects.registry.get_repository_status",
        lambda repository: {
            "status": "unknown",
            "source": "github_public_api",
            "observed_at": "2026-11-08T12:00:00+00:00",
            "reason_code": "github_rate_limited",
            "repository": repository,
            "default_branch": None,
            "latest_commit": None,
            "open_pull_requests": [],
            "open_pull_requests_sample_size": 0,
            "open_pull_requests_may_be_truncated": False,
            "latest_ci": {"status": "unknown", "source": "github_actions_public_api",
                          "observed_at": "2026-11-08T12:00:00+00:00",
                          "reason_code": "github_rate_limited"},
        },
    )
    monkeypatch.setenv("MRH_DATABASE_PATH", str(tmp_path / "projects.sqlite3"))
    get_settings.cache_clear()
    client = TestClient(create_app())
    client.post("/auth/setup", json={"password": "test-only-strong" + "-password-2026"})
    login = client.post(
        "/auth/login",
        json={"username": "owner", "password": "test-only-strong" + "-password-2026"},
    )
    client.headers.update({"Authorization": f"Bearer {login.json()['access_token']}"})

    projects = client.get("/projects/registry").json()["projects"]

    assert not any(project["runtime_status"] == "healthy" for project in projects)
    assert not any(project["repository_status"] == "healthy" for project in projects)
