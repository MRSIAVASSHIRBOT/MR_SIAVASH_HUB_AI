"""Read-only discovery of public GitHub repository metadata.

Only the fixed GitHub API host is contacted. Repository source code is never fetched,
installed, imported, or executed by this discovery layer.
"""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlsplit

import httpx

from mrhub.capabilities.metadata_evaluation import evaluate_repository_metadata
from mrhub.capabilities.registry import (
    CapabilityCandidate,
    CapabilityRegistry,
    CapabilityValidationError,
    canonicalize_source_url,
)

_GITHUB_REPOSITORY_PATH = re.compile(r"^/([A-Za-z0-9_.-]{1,100})/([A-Za-z0-9_.-]{1,100})/?$")
_MAX_RESPONSE_BYTES = 1_000_000
_USER_AGENT = "MR-SIAVASH-HUB-AI-CapabilityDiscovery/0.1"


class GitHubDiscoveryError(RuntimeError):
    """A safe, user-facing error while inspecting public GitHub metadata."""

    def __init__(self, code: str, message: str, *, status_code: int = 422) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code


def parse_github_repository_url(source_url: str) -> tuple[str, str, str]:
    """Return owner, repository, and canonical URL for a GitHub repository URL."""
    canonical = canonicalize_source_url(source_url)
    parsed = urlsplit(canonical)
    if parsed.hostname != "github.com":
        raise CapabilityValidationError("Only public github.com repository URLs are supported")
    match = _GITHUB_REPOSITORY_PATH.fullmatch(parsed.path)
    if match is None:
        raise CapabilityValidationError("Use a repository URL in the form https://github.com/OWNER/REPO")
    owner, repository = match.groups()
    if repository.lower().endswith(".git"):
        repository = repository[:-4]
    if not repository:
        raise CapabilityValidationError("Repository name is missing")
    return owner, repository, f"https://github.com/{owner}/{repository}"


def _metadata_response(source_url: str) -> dict[str, Any]:
    owner, repository, _canonical_url = parse_github_repository_url(source_url)
    api_url = f"https://api.github.com/repos/{owner}/{repository}"
    try:
        with httpx.Client(
            timeout=httpx.Timeout(5.0, connect=3.0),
            follow_redirects=False,
            trust_env=False,
            headers={
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": _USER_AGENT,
            },
        ) as client:
            with client.stream("GET", api_url) as response:
                if response.status_code == 404:
                    raise GitHubDiscoveryError("repository_not_found", "Public repository not found", status_code=404)
                if response.status_code == 403 and response.headers.get("x-ratelimit-remaining") == "0":
                    raise GitHubDiscoveryError("github_rate_limited", "GitHub API rate limit reached; try again later", status_code=429)
                if response.status_code == 401:
                    raise GitHubDiscoveryError("github_api_auth_required", "GitHub API refused this metadata request", status_code=502)
                if response.status_code == 403:
                    raise GitHubDiscoveryError("github_api_forbidden", "GitHub API denied this metadata request", status_code=502)
                if response.status_code >= 500:
                    raise GitHubDiscoveryError("github_unavailable", "GitHub API is temporarily unavailable", status_code=502)
                if response.status_code != 200:
                    raise GitHubDiscoveryError("github_api_error", f"GitHub API returned HTTP {response.status_code}", status_code=502)
                chunks: list[bytes] = []
                total = 0
                for chunk in response.iter_bytes():
                    total += len(chunk)
                    if total > _MAX_RESPONSE_BYTES:
                        raise GitHubDiscoveryError("metadata_response_too_large", "GitHub metadata response exceeded the size limit", status_code=502)
                    chunks.append(chunk)
                try:
                    payload = httpx.Response(200, content=b"".join(chunks)).json()
                except ValueError as exc:
                    raise GitHubDiscoveryError("invalid_github_response", "GitHub returned invalid metadata JSON", status_code=502) from exc
    except GitHubDiscoveryError:
        raise
    except httpx.TimeoutException as exc:
        raise GitHubDiscoveryError("github_timeout", "GitHub metadata request timed out", status_code=504) from exc
    except httpx.HTTPError as exc:
        raise GitHubDiscoveryError("github_network_error", "Could not retrieve GitHub repository metadata", status_code=502) from exc
    if not isinstance(payload, dict) or payload.get("full_name") is None:
        raise GitHubDiscoveryError("invalid_github_response", "GitHub response is missing repository metadata", status_code=502)
    return payload


def discover_github_candidate(source_url: str, registry: CapabilityRegistry) -> tuple[CapabilityCandidate, dict[str, Any]]:
    """Inspect public repo metadata and persist a review candidate; never execute code."""
    owner, repository, canonical_url = parse_github_repository_url(source_url)
    metadata = _metadata_response(canonical_url)
    license_data = metadata.get("license")
    license_id = "unknown"
    if isinstance(license_data, dict):
        spdx_id = license_data.get("spdx_id")
        if isinstance(spdx_id, str) and spdx_id.strip() not in {"", "NOASSERTION"}:
            license_id = spdx_id.strip()[:80]
    topics = metadata.get("topics", [])
    capabilities = [topic for topic in topics if isinstance(topic, str)][:50] if isinstance(topics, list) else []
    language = metadata.get("language")
    if isinstance(language, str) and language.strip() and len(capabilities) < 50:
        capabilities.append(f"language:{language.strip()[:70]}")
    description = metadata.get("description")
    summary = description.strip()[:1000] if isinstance(description, str) else ""
    display_name = str(metadata.get("full_name") or f"{owner}/{repository}")[:160]
    try:
        candidate = registry.add_candidate(
            source_url=canonical_url,
            display_name=display_name,
            summary=summary,
            source_kind="github_repository",
            integration_type="manual",
            capabilities=capabilities,
            license_id=license_id,
        )
    except CapabilityValidationError as exc:
        if "already in the catalog" in str(exc):
            raise GitHubDiscoveryError("candidate_already_registered", "This repository is already in the capability catalog", status_code=409) from exc
        raise
    safe_metadata = {
        "full_name": display_name,
        "html_url": canonical_url,
        "description": summary,
        "default_branch": str(metadata.get("default_branch") or "")[:255],
        "language": language if isinstance(language, str) else None,
        "topics": capabilities[:50],
        "license_spdx_id": license_id,
        "archived": bool(metadata.get("archived", False)),
        "disabled": bool(metadata.get("disabled", False)),
        "fork": bool(metadata.get("fork", False)),
        "stargazers_count": max(0, int(metadata.get("stargazers_count", 0) or 0)),
        "open_issues_count": max(0, int(metadata.get("open_issues_count", 0) or 0)),
        "updated_at": str(metadata.get("updated_at") or "")[:40],
        "candidate": candidate.as_dict(),
        "evaluation": evaluate_repository_metadata(metadata),
        "source_code_fetched": False,
        "source_code_executed": False,
        "installation_started": False,
        "approval_granted": False,
    }
    return candidate, safe_metadata
