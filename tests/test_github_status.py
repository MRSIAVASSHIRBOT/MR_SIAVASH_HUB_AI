import httpx
import pytest

from mrhub.integrations import github_status
from mrhub.integrations.github_status import GitHubStatusClient, GitHubStatusError

REPOSITORY = "MRSIAVASSHIRBOT/MR_SIAVASH_AI"
SHA = "a" * 40
_ORIGINAL_HTTPX_CLIENT = httpx.Client


def _metadata():
    return {
        "full_name": REPOSITORY,
        "default_branch": "main",
        "archived": False,
        "updated_at": "2026-11-08T11:55:00Z",
    }


def _commit():
    return {
        "sha": SHA,
        "commit": {
            "message": "feat: publish the website\n\nAdditional details",
            "author": {"date": "2026-11-08T11:50:00Z"},
        },
    }


def test_github_status_uses_only_fixed_public_api_paths_and_projects_metadata(monkeypatch):
    calls = []

    def handler(request):
        calls.append(request)
        if request.url.path == f"/repos/{REPOSITORY}":
            return httpx.Response(200, json=_metadata())
        if request.url.path == f"/repos/{REPOSITORY}/commits/main":
            return httpx.Response(200, json=_commit())
        if request.url.path == f"/repos/{REPOSITORY}/pulls":
            assert dict(request.url.params) == {"state": "open", "per_page": "10"}
            return httpx.Response(200, json=[{
                "number": 71,
                "title": "Publish and verify the static site",
                "updated_at": "2026-11-08T11:40:00Z",
            }])
        if request.url.path == f"/repos/{REPOSITORY}/actions/runs":
            assert dict(request.url.params) == {"branch": "main", "per_page": "1"}
            return httpx.Response(200, json={"workflow_runs": [{
                "id": 12345,
                "name": "Quality checks and GitHub Pages deployment",
                "status": "completed",
                "conclusion": "success",
                "updated_at": "2026-11-08T11:56:00Z",
            }]})
        raise AssertionError(f"unexpected GitHub endpoint: {request.url}")

    def client_factory(**kwargs):
        return _ORIGINAL_HTTPX_CLIENT(
            transport=httpx.MockTransport(handler),
            **kwargs,
        )

    monkeypatch.setattr(github_status.httpx, "Client", client_factory)
    result = GitHubStatusClient().read_repository_status(REPOSITORY)

    assert result["status"] == "healthy"
    assert result["source"] == "github_public_api"
    assert result["default_branch"] == "main"
    assert result["latest_commit"]["sha"] == SHA
    assert result["latest_commit"]["message"] == "feat: publish the website"
    assert result["latest_commit"]["url"] == f"https://github.com/{REPOSITORY}/commit/{SHA}"
    assert result["open_pull_requests"][0]["url"] == (
        f"https://github.com/{REPOSITORY}/pull/71"
    )
    assert result["latest_ci"]["status"] == "healthy"
    assert result["latest_ci"]["url"].endswith("/actions/runs/12345")
    assert len(calls) == 4
    assert all(request.url.host == "api.github.com" for request in calls)
    assert all(request.method == "GET" for request in calls)


def test_github_status_rejects_unenrolled_or_malformed_repository_before_network(monkeypatch):
    client = GitHubStatusClient()

    def no_network(_path):
        pytest.fail("invalid repository must not trigger a network request")

    monkeypatch.setattr(client, "_get_json", no_network)
    result = client.read_repository_status("https://attacker.example/owner/repo")

    assert result["status"] == "unknown"
    assert result["reason_code"] == "invalid_repository"


def test_github_rate_limit_returns_unknown_without_leaking_upstream_body(monkeypatch):
    client = GitHubStatusClient()

    def rate_limited(_path):
        raise GitHubStatusError("github_rate_limited")

    monkeypatch.setattr(client, "_get_json", rate_limited)
    result = client.read_repository_status(REPOSITORY)

    assert result["status"] == "unknown"
    assert result["reason_code"] == "github_rate_limited"
    assert "token" not in str(result).lower()


def test_archived_repository_is_degraded_and_ci_failure_is_explicit(monkeypatch):
    client = GitHubStatusClient()

    def fake_get(path):
        if path == f"/repos/{REPOSITORY}":
            data = _metadata()
            data["archived"] = True
            return data
        if path.endswith("/commits/main"):
            return _commit()
        if path.endswith("/pulls?state=open&per_page=10"):
            return []
        if path.endswith("/actions/runs?per_page=1"):
            return {"workflow_runs": [{
                "id": 99,
                "status": "completed",
                "conclusion": "failure",
            }]}
        raise AssertionError(path)

    monkeypatch.setattr(client, "_get_json", fake_get)
    result = client.read_repository_status(REPOSITORY)

    assert result["status"] == "degraded"
    assert result["reason_code"] == "repository_archived"
    assert result["latest_ci"]["status"] == "failing"


def test_gitHub_status_client_rejects_unbounded_limits():
    with pytest.raises(ValueError):
        GitHubStatusClient(timeout_seconds=5.1)
    with pytest.raises(ValueError):
        GitHubStatusClient(max_response_bytes=262_145)


def test_latest_ci_is_scoped_to_default_branch_not_newer_feature_branch(monkeypatch):
    client = GitHubStatusClient()
    requested = []

    def fake_get(path):
        if path == f"/repos/{REPOSITORY}":
            return _metadata()
        if path.endswith("/commits/main"):
            return _commit()
        if path.endswith("/pulls?state=open&per_page=10"):
            return []
        if "/actions/runs?" in path:
            requested.append(path)
            assert path.endswith("/actions/runs?branch=main&per_page=1")
            # The default-branch run is failing. A newer feature-branch success
            # must not be used as the repository's default-branch CI signal.
            return {"workflow_runs": [{
                "id": 501,
                "name": "Default branch checks",
                "head_branch": "main",
                "status": "completed",
                "conclusion": "failure",
            }]}
        raise AssertionError(path)

    monkeypatch.setattr(client, "_get_json", fake_get)
    result = client.read_repository_status(REPOSITORY)

    assert requested == [f"/repos/{REPOSITORY}/actions/runs?branch=main&per_page=1"]
    assert result["latest_ci"]["status"] == "failing"
    assert result["latest_ci"]["workflow_name"] == "Default branch checks"


def test_repository_status_cache_reuses_result_and_returns_defensive_copies(monkeypatch):
    github_status._clear_status_cache()
    calls = []

    def fake_read(self, repository):
        calls.append(repository)
        return {
            "status": "healthy",
            "repository": repository,
            "default_branch": "main",
            "latest_ci": {"status": "healthy"},
        }

    monkeypatch.setattr(GitHubStatusClient, "read_repository_status", fake_read)
    first = github_status.get_repository_status(REPOSITORY)
    first["latest_ci"]["status"] = "tampered"
    second = github_status.get_repository_status(REPOSITORY)

    assert len(calls) == 1
    assert second["latest_ci"]["status"] == "healthy"
    github_status._clear_status_cache()


def test_repository_status_cache_expires_and_unknown_results_use_short_ttl(monkeypatch):
    github_status._clear_status_cache()
    clock = [100.0]
    calls = []

    class FakeClient:
        def read_repository_status(self, repository):
            calls.append(repository)
            if len(calls) == 1:
                return {
                    "status": "healthy",
                    "repository": repository,
                    "default_branch": "main",
                }
            return {
                "status": "unknown",
                "repository": repository,
                "default_branch": None,
                "reason_code": "github_rate_limited",
            }

    monkeypatch.setattr(github_status.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(github_status, "GitHubStatusClient", FakeClient)

    assert github_status.get_repository_status(REPOSITORY)["status"] == "healthy"
    assert github_status.get_repository_status(REPOSITORY)["status"] == "healthy"
    assert len(calls) == 1

    clock[0] += github_status.STATUS_CACHE_TTL_SECONDS + 0.1
    assert github_status.get_repository_status(REPOSITORY)["status"] == "unknown"
    assert len(calls) == 2
    assert github_status.get_repository_status(REPOSITORY)["status"] == "unknown"
    assert len(calls) == 2

    clock[0] += github_status.STATUS_CACHE_FAILURE_TTL_SECONDS + 0.1
    assert github_status.get_repository_status(REPOSITORY)["status"] == "unknown"
    assert len(calls) == 3
    github_status._clear_status_cache()
