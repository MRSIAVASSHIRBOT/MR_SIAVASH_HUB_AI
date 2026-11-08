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
    if owner in {".", ".."} or repository in {".", ".."}:
        raise CapabilityValidationError("Owner and repository names must be valid path segments")
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
        ) as client, client.stream("GET", api_url) as response:
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
    _validate_repository_identity(payload, owner, repository)
    return payload


def _validate_repository_identity(
    metadata: object, expected_owner: str, expected_repository: str
) -> None:
    """Reject malformed or mismatched upstream identity before persisting metadata."""
    if not isinstance(metadata, dict):
        raise GitHubDiscoveryError(
            "invalid_github_response", "GitHub returned an invalid metadata object", status_code=502
        )
    full_name = metadata.get("full_name")
    if not isinstance(full_name, str) or full_name.count("/") != 1:
        raise GitHubDiscoveryError(
            "invalid_github_response", "GitHub response is missing a valid repository identity", status_code=502
        )
    actual_owner, actual_repository = (part.strip() for part in full_name.split("/", 1))
    if (
        not actual_owner
        or not actual_repository
        or actual_owner.casefold() != expected_owner.casefold()
        or actual_repository.casefold() != expected_repository.casefold()
    ):
        raise GitHubDiscoveryError(
            "github_repository_mismatch",
            "GitHub metadata identity did not match the requested repository",
            status_code=502,
        )


def _safe_public_flag(value: object) -> bool:
    """Accept only actual JSON booleans; strings such as 'false' are not truthy flags."""
    return value if isinstance(value, bool) else False


def _safe_public_text(value: object, limit: int) -> str | None:
    """Normalize optional upstream text to a bounded, non-empty string."""
    if not isinstance(value, str):
        return None
    normalized = value.strip()[:limit]
    return normalized or None


def _safe_public_count(value: object) -> int:
    """Normalize public counters without letting malformed upstream values crash discovery."""
    if isinstance(value, bool):
        return 0
    try:
        count = int(value or 0)
    except (TypeError, ValueError, OverflowError):
        return 0
    return max(0, min(count, 2_147_483_647))


def discover_github_candidate(source_url: str, registry: CapabilityRegistry) -> tuple[CapabilityCandidate, dict[str, Any]]:
    """Inspect public repo metadata and persist a review candidate; never execute code."""
    owner, repository, canonical_url = parse_github_repository_url(source_url)
    metadata = _metadata_response(canonical_url)
    _validate_repository_identity(metadata, owner, repository)
    license_data = metadata.get("license")
    license_id = "unknown"
    if isinstance(license_data, dict):
        spdx_id = license_data.get("spdx_id")
        if isinstance(spdx_id, str) and spdx_id.strip() not in {"", "NOASSERTION"}:
            license_id = spdx_id.strip()[:80]
    topics = metadata.get("topics", [])
    capabilities: list[str] = []
    if isinstance(topics, list):
        for topic in topics:
            normalized_topic = _safe_public_text(topic, 80)
            if normalized_topic:
                capabilities.append(normalized_topic)
            if len(capabilities) >= 50:
                break
    language = _safe_public_text(metadata.get("language"), 70)
    if language and len(capabilities) < 50:
        capabilities.append(f"language:{language}")
    description = _safe_public_text(metadata.get("description"), 1000) or ""
    display_name = _safe_public_text(metadata.get("full_name"), 160)
    if display_name is None:
        raise GitHubDiscoveryError(
            "invalid_github_response", "GitHub response is missing a valid repository identity", status_code=502
        )
    archived = _safe_public_flag(metadata.get("archived"))
    disabled = _safe_public_flag(metadata.get("disabled"))
    fork = _safe_public_flag(metadata.get("fork"))
    default_branch = _safe_public_text(metadata.get("default_branch"), 255) or ""
    updated_at = _safe_public_text(metadata.get("updated_at"), 40) or ""
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
        "default_branch": default_branch,
        "language": language,
        "topics": capabilities[:50],
        "license_spdx_id": license_id,
        "archived": archived,
        "disabled": disabled,
        "fork": fork,
        "stargazers_count": _safe_public_count(metadata.get("stargazers_count", 0)),
        "open_issues_count": _safe_public_count(metadata.get("open_issues_count", 0)),
        "updated_at": updated_at,
        "candidate": candidate.as_dict(),
        "evaluation": evaluate_repository_metadata({
            **metadata,
            "archived": archived,
            "disabled": disabled,
            "fork": fork,
            "stargazers_count": _safe_public_count(metadata.get("stargazers_count", 0)),
            "updated_at": updated_at,
        }),
        "source_code_fetched": False,
        "source_code_executed": False,
        "installation_started": False,
        "approval_granted": False,
    }
    return candidate, safe_metadata
