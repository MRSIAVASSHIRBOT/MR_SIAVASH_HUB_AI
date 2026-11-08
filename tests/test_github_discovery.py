from __future__ import annotations

import json
from typing import ClassVar

import pytest

from mrhub.capabilities.github_discovery import (
    GitHubDiscoveryError,
    _metadata_response,
    discover_github_candidate,
    parse_github_repository_url,
)
from mrhub.capabilities.registry import CapabilityRegistry, CapabilityValidationError


def test_parse_github_repository_url_normalizes_git_suffix():
    assert parse_github_repository_url("https://github.com/Example/Tool.git/") == (
        "Example", "Tool", "https://github.com/Example/Tool"
    )


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/owner/repo",
        "https://github.com/owner",
        "https://github.com/owner/repo/issues",
        "https://github.com/owner/repo?token=secret",
        "https://github.com/../repo",
        "https://github.com/owner/..",
        "http://github.com/owner/repo",
    ],
)
def test_parse_github_repository_url_rejects_non_repository_urls(url):
    with pytest.raises(CapabilityValidationError):
        parse_github_repository_url(url)


def test_metadata_request_uses_fixed_github_api_host_and_bounded_timeout(monkeypatch):
    calls = []

    class FakeResponse:
        status_code = 200
        headers: ClassVar[dict[str, str]] = {}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def iter_bytes(self):
            yield json.dumps({"full_name": "Example/Tool"}).encode()

    class FakeClient:
        def __init__(self, **kwargs):
            calls.append(("init", kwargs))

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def stream(self, method, url):
            calls.append((method, url))
            return FakeResponse()

    monkeypatch.setattr("mrhub.capabilities.github_discovery.httpx.Client", FakeClient)
    assert _metadata_response("https://github.com/Example/Tool")["full_name"] == "Example/Tool"
    assert calls[1] == ("GET", "https://api.github.com/repos/Example/Tool")
    assert calls[0][1]["follow_redirects"] is False
    assert calls[0][1]["trust_env"] is False


def test_discovery_registers_metadata_only_candidate_and_never_approves(monkeypatch, tmp_path):
    metadata = {
        "full_name": "Example/VideoTool",
        "description": "A video helper.",
        "default_branch": "main",
        "language": "Python",
        "topics": ["video", "ai"],
        "license": {"spdx_id": "MIT"},
        "archived": False,
        "disabled": False,
        "fork": False,
        "stargazers_count": 123,
        "open_issues_count": 4,
        "updated_at": "2026-10-30T12:00:00Z",
    }
    monkeypatch.setattr("mrhub.capabilities.github_discovery._metadata_response", lambda url: metadata)
    registry = CapabilityRegistry(tmp_path / "discovery.sqlite3")

    candidate, result = discover_github_candidate("https://github.com/Example/VideoTool", registry)

    assert candidate.status == "discovered"
    assert candidate.license_id == "MIT"
    assert candidate.capabilities == ("video", "ai", "language:Python")
    assert result["source_code_fetched"] is False
    assert result["source_code_executed"] is False
    assert result["approval_granted"] is False
    assert result["stargazers_count"] == 123
    assert result["evaluation"]["scope"] == "metadata_only"
    assert result["evaluation"]["approval_granted"] is False


def test_github_404_becomes_safe_not_found_error(monkeypatch):
    class FakeResponse:
        status_code = 404
        headers: ClassVar[dict[str, str]] = {}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def iter_bytes(self):
            yield b"{}"

    class FakeClient:
        def __init__(self, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def stream(self, method, url): return FakeResponse()

    monkeypatch.setattr("mrhub.capabilities.github_discovery.httpx.Client", FakeClient)
    with pytest.raises(GitHubDiscoveryError) as error:
        _metadata_response("https://github.com/Example/Missing")
    assert error.value.code == "repository_not_found"
    assert error.value.status_code == 404


def test_malformed_public_counters_are_bounded_instead_of_crashing(monkeypatch, tmp_path):
    metadata = {
        "full_name": "Example/BadCounters",
        "stargazers_count": "not-an-integer",
        "open_issues_count": -9,
        "license": {"spdx_id": "MIT"},
        "archived": False,
        "disabled": False,
        "fork": False,
    }
    monkeypatch.setattr("mrhub.capabilities.github_discovery._metadata_response", lambda url: metadata)
    registry = CapabilityRegistry(tmp_path / "bad-counters.sqlite3")

    _candidate, result = discover_github_candidate("https://github.com/Example/BadCounters", registry)

    assert result["stargazers_count"] == 0
    assert result["open_issues_count"] == 0


@pytest.mark.parametrize(
    ("payload", "expected_code"),
    [
        ({"full_name": None}, "invalid_github_response"),
        ({"full_name": ["Example", "Tool"]}, "invalid_github_response"),
        ({"full_name": "Example/Other"}, "github_repository_mismatch"),
    ],
)
def test_metadata_response_rejects_malformed_or_mismatched_repository_identity(
    monkeypatch, payload, expected_code
):
    class FakeResponse:
        status_code = 200
        headers: ClassVar[dict[str, str]] = {}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def iter_bytes(self):
            yield json.dumps(payload).encode()

    class FakeClient:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def stream(self, method, url):
            return FakeResponse()

    monkeypatch.setattr("mrhub.capabilities.github_discovery.httpx.Client", FakeClient)

    with pytest.raises(GitHubDiscoveryError) as error:
        _metadata_response("https://github.com/Example/Tool")

    assert error.value.code == expected_code
    assert error.value.status_code == 502


def test_discovery_normalizes_untrusted_metadata_types_and_bounds_text(monkeypatch, tmp_path):
    metadata = {
        "full_name": "Example/Sanitized",
        "description": "  Safe summary  ",
        "default_branch": "  " + ("b" * 300),
        "language": "  " + ("L" * 100),
        "topics": ["  " + ("T" * 120)],
        "license": {"spdx_id": "MIT"},
        "archived": False,
        "disabled": False,
        "fork": False,
        "stargazers_count": 12,
        "open_issues_count": 3,
        "updated_at": "  2026-11-01T00:00:00Z  ",
    }
    monkeypatch.setattr(
        "mrhub.capabilities.github_discovery._metadata_response", lambda url: metadata
    )
    registry = CapabilityRegistry(tmp_path / "sanitized-metadata.sqlite3")

    candidate, result = discover_github_candidate(
        "https://github.com/Example/Sanitized", registry
    )

    assert candidate.capabilities == ("T" * 80, "language:" + "L" * 70)
    assert result["description"] == "Safe summary"
    assert result["default_branch"] == "b" * 255
    assert result["language"] == "L" * 70
    assert result["archived"] is False
    assert result["disabled"] is False
    assert result["fork"] is False
    assert result["updated_at"] == "2026-11-01T00:00:00Z"
    assert "repository_inactive" not in {
        signal["code"] for signal in result["evaluation"]["signals"]
    }
    assert "repository_is_fork" not in {
        signal["code"] for signal in result["evaluation"]["signals"]
    }


@pytest.mark.parametrize("field", ["archived", "disabled", "fork"])
@pytest.mark.parametrize("invalid_value", ["true", "false", "0", 1, None])
def test_discovery_rejects_malformed_repository_state_flags(
    monkeypatch, tmp_path, field, invalid_value
):
    metadata = {
        "full_name": "Example/FlagValidation",
        "license": {"spdx_id": "MIT"},
        "archived": False,
        "disabled": False,
        "fork": False,
    }
    metadata[field] = invalid_value
    monkeypatch.setattr(
        "mrhub.capabilities.github_discovery._metadata_response", lambda url: metadata
    )
    registry = CapabilityRegistry(tmp_path / f"invalid-{field}.sqlite3")

    with pytest.raises(GitHubDiscoveryError) as error:
        discover_github_candidate("https://github.com/Example/FlagValidation", registry)

    assert error.value.code == "invalid_github_response"
    assert error.value.status_code == 502
