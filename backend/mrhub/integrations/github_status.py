"""Bounded, read-only status observations for explicitly enrolled public GitHub repos.

This adapter never accepts arbitrary URLs, fetches repository source, or performs
writes. It uses GitHub's public REST API without credentials; private repositories
and rate-limited observations remain unknown rather than being guessed.
"""
from __future__ import annotations

import json
import re
import time
from collections import OrderedDict
from copy import deepcopy
from datetime import UTC, datetime
from threading import RLock
from typing import Any
from urllib.parse import quote

import httpx

API_ROOT = "https://api.github.com"
REQUEST_TIMEOUT_SECONDS = 5.0
MAX_RESPONSE_BYTES = 262_144
MAX_PULL_REQUESTS = 10
STATUS_CACHE_TTL_SECONDS = 30.0
STATUS_CACHE_FAILURE_TTL_SECONDS = 5.0
STATUS_CACHE_MAX_ENTRIES = 128
_STATUS_CACHE: OrderedDict[tuple[str, str], tuple[float, dict[str, Any]]] = OrderedDict()
_STATUS_CACHE_INDEX: dict[str, tuple[str, float]] = {}
_STATUS_CACHE_LOCK = RLock()
_REPOSITORY_PATTERN = re.compile(r"^([A-Za-z0-9_.-]{1,100})/([A-Za-z0-9_.-]{1,100})$")
_BRANCH_PATTERN = re.compile(r"^[A-Za-z0-9_./-]{1,255}$")
_SHA_PATTERN = re.compile(r"^[a-f0-9]{40}$")
_USER_AGENT = "MR-SIAVASH-HUB-AI-ProjectStatus/1.0"


class GitHubStatusError(RuntimeError):
    """Sanitized error from a read-only GitHub status request."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class GitHubStatusClient:
    """Fetch a small, fixed set of public repository status metadata."""

    def __init__(self, *, timeout_seconds: float = REQUEST_TIMEOUT_SECONDS,
                 max_response_bytes: int = MAX_RESPONSE_BYTES) -> None:
        if (isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float))
                or not 0 < timeout_seconds <= REQUEST_TIMEOUT_SECONDS):
            raise ValueError("Invalid GitHub status timeout")
        if (isinstance(max_response_bytes, bool) or not isinstance(max_response_bytes, int)
                or not 1 <= max_response_bytes <= MAX_RESPONSE_BYTES):
            raise ValueError("Invalid GitHub status response limit")
        self._timeout = float(timeout_seconds)
        self._max_response_bytes = max_response_bytes

    def _get_json(self, path: str) -> Any:
        # Only module-owned fixed endpoint templates are accepted.
        if not path.startswith("/repos/") or "://" in path or "#" in path:
            raise GitHubStatusError("invalid_github_operation")
        url = API_ROOT + path
        try:
            with httpx.Client(
                timeout=httpx.Timeout(self._timeout, connect=min(3.0, self._timeout)),
                follow_redirects=False,
                trust_env=False,
                headers={
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                    "User-Agent": _USER_AGENT,
                },
            ) as client, client.stream("GET", url) as response:
                if response.is_redirect:
                    raise GitHubStatusError("github_redirect_rejected")
                if response.status_code == 404:
                    raise GitHubStatusError("repository_not_found")
                if response.status_code == 403 and response.headers.get("x-ratelimit-remaining") == "0":
                    raise GitHubStatusError("github_rate_limited")
                if response.status_code == 403:
                    raise GitHubStatusError("github_forbidden")
                if response.status_code >= 500:
                    raise GitHubStatusError("github_unavailable")
                if response.status_code != 200:
                    raise GitHubStatusError("github_http_error")
                content_type = response.headers.get("content-type", "")
                if not content_type.lower().startswith("application/json"):
                    raise GitHubStatusError("github_invalid_content_type")
                declared = response.headers.get("content-length")
                if declared is not None:
                    try:
                        if int(declared) > self._max_response_bytes:
                            raise GitHubStatusError("github_response_too_large")
                    except ValueError:
                        raise GitHubStatusError("github_invalid_response") from None
                body = bytearray()
                for chunk in response.iter_bytes(chunk_size=min(8192, self._max_response_bytes + 1)):
                    body.extend(chunk)
                    if len(body) > self._max_response_bytes:
                        raise GitHubStatusError("github_response_too_large")
        except GitHubStatusError:
            raise
        except httpx.TimeoutException:
            raise GitHubStatusError("github_timeout") from None
        except (httpx.HTTPError, OSError, ValueError):
            raise GitHubStatusError("github_network_error") from None
        try:
            payload = json.loads(body)
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise GitHubStatusError("github_invalid_json") from None
        if not isinstance(payload, (dict, list)):
            raise GitHubStatusError("github_invalid_response")
        return payload

    @staticmethod
    def _repo_parts(repository: str) -> tuple[str, str]:
        if not isinstance(repository, str):
            raise GitHubStatusError("invalid_repository")
        match = _REPOSITORY_PATTERN.fullmatch(repository)
        if match is None or any(part in {".", ".."} for part in match.groups()):
            raise GitHubStatusError("invalid_repository")
        return match.group(1), match.group(2)

    @staticmethod
    def _unknown(repository: str, observed_at: str, code: str) -> dict[str, Any]:
        return {
            "status": "unknown",
            "source": "github_public_api",
            "observed_at": observed_at,
            "reason_code": code,
            "repository": repository,
            "default_branch": None,
            "latest_commit": None,
            "open_pull_requests": [],
            "open_pull_requests_sample_size": 0,
            "open_pull_requests_may_be_truncated": False,
            "latest_ci": {
                "status": "unknown",
                "source": "github_actions_public_api",
                "observed_at": observed_at,
                "reason_code": code,
            },
        }

    def read_repository_status(self, repository: str) -> dict[str, Any]:
        """Return projected repository, commit, PR and latest-CI observations."""
        observed_at = datetime.now(UTC).isoformat()
        try:
            owner, name = self._repo_parts(repository)
        except GitHubStatusError as exc:
            return self._unknown(str(repository)[:205], observed_at, exc.code)
        prefix = f"/repos/{owner}/{name}"
        try:
            metadata = self._get_json(prefix)
        except GitHubStatusError as exc:
            return self._unknown(repository, observed_at, exc.code)
        if (not isinstance(metadata, dict) or metadata.get("full_name") != repository
                or not isinstance(metadata.get("archived"), bool)
                or not isinstance(metadata.get("default_branch"), str)
                or not _BRANCH_PATTERN.fullmatch(metadata["default_branch"])):
            return self._unknown(repository, observed_at, "github_invalid_repository_metadata")

        default_branch = metadata["default_branch"]
        archived = metadata.get("archived") is True
        latest_commit = None
        commit_error = "github_commit_unavailable"
        try:
            commit = self._get_json(prefix + "/commits/" + quote(default_branch, safe=""))
            if isinstance(commit, dict):
                sha = commit.get("sha")
                details = commit.get("commit")
                message = details.get("message") if isinstance(details, dict) else None
                author = details.get("author") if isinstance(details, dict) else None
                date = author.get("date") if isinstance(author, dict) else None
                if isinstance(sha, str) and _SHA_PATTERN.fullmatch(sha):
                    latest_commit = {
                        "sha": sha,
                        "message": message.splitlines()[0][:200] if isinstance(message, str) else "",
                        "committed_at": date[:40] if isinstance(date, str) else None,
                        "url": f"https://github.com/{owner}/{name}/commit/{sha}",
                    }
        except GitHubStatusError as exc:
            commit_error = exc.code

        pull_requests: list[dict[str, Any]] = []
        pulls_error = "github_pull_requests_unavailable"
        pulls_observed = False
        try:
            records = self._get_json(prefix + "/pulls?state=open&per_page=10")
            if isinstance(records, list):
                pulls_observed = True
                for item in records[:MAX_PULL_REQUESTS]:
                    if not isinstance(item, dict):
                        continue
                    number = item.get("number")
                    title = item.get("title")
                    if (isinstance(number, int) and not isinstance(number, bool) and number > 0
                            and isinstance(title, str)):
                        pull_requests.append({
                            "number": number,
                            "title": title[:200],
                            "updated_at": item.get("updated_at")[:40]
                                if isinstance(item.get("updated_at"), str) else None,
                            "url": f"https://github.com/{owner}/{name}/pull/{number}",
                        })
        except GitHubStatusError as exc:
            pulls_error = exc.code

        latest_ci: dict[str, Any] = {
            "status": "unknown",
            "source": "github_actions_public_api",
            "observed_at": observed_at,
            "branch": default_branch,
            "reason_code": "github_workflow_runs_unavailable",
        }
        try:
            runs = self._get_json(
                prefix + "/actions/runs?branch=" + quote(default_branch, safe="")
                + "&per_page=1"
            )
            workflow_runs = runs.get("workflow_runs") if isinstance(runs, dict) else None
            if isinstance(workflow_runs, list) and workflow_runs:
                run = workflow_runs[0]
                if isinstance(run, dict):
                    run_status = run.get("status")
                    conclusion = run.get("conclusion")
                    if run_status == "completed" and conclusion == "success":
                        ci_status, reason = "healthy", "latest_workflow_succeeded"
                    elif run_status == "completed" and conclusion in {
                        "failure", "timed_out", "action_required"
                    }:
                        ci_status, reason = "failing", "latest_workflow_failed"
                    elif run_status in {"queued", "in_progress", "waiting", "requested"}:
                        ci_status, reason = "degraded", "latest_workflow_in_progress"
                    else:
                        ci_status, reason = "unknown", "latest_workflow_state_unknown"
                    run_id = run.get("id")
                    latest_ci = {
                        "status": ci_status,
                        "source": "github_actions_public_api",
                        "observed_at": observed_at,
                        "branch": default_branch,
                        "reason_code": reason,
                        "workflow_name": str(run.get("name") or "")[:120],
                        "conclusion": conclusion if isinstance(conclusion, str) else None,
                        "updated_at": run.get("updated_at")[:40]
                            if isinstance(run.get("updated_at"), str) else None,
                        "url": f"https://github.com/{owner}/{name}/actions/runs/{run_id}"
                            if isinstance(run_id, int) and not isinstance(run_id, bool) else None,
                    }
        except GitHubStatusError as exc:
            latest_ci["reason_code"] = exc.code

        return {
            "status": "degraded" if archived else "healthy",
            "source": "github_public_api",
            "observed_at": observed_at,
            "reason_code": "repository_archived" if archived else "repository_metadata_observed",
            "repository": repository,
            "default_branch": default_branch,
            "archived": archived,
            "updated_at": metadata.get("updated_at")[:40]
                if isinstance(metadata.get("updated_at"), str) else None,
            "latest_commit": latest_commit,
            "latest_commit_reason_code": None if latest_commit else commit_error,
            "open_pull_requests": pull_requests,
            "open_pull_requests_sample_size": len(pull_requests),
            "open_pull_requests_may_be_truncated": len(pull_requests) == MAX_PULL_REQUESTS,
            "pull_requests_reason_code": None if pulls_observed else pulls_error,
            "latest_ci": latest_ci,
        }


def _cached_repository_status(repository: str, now: float) -> dict[str, Any] | None:
    """Return a defensive copy of an unexpired process-local cache entry."""
    with _STATUS_CACHE_LOCK:
        index = _STATUS_CACHE_INDEX.get(repository)
        if index is None:
            return None
        branch, expires_at = index
        key = (repository, branch)
        entry = _STATUS_CACHE.get(key)
        if entry is None or expires_at <= now or entry[0] <= now:
            _STATUS_CACHE_INDEX.pop(repository, None)
            _STATUS_CACHE.pop(key, None)
            return None
        _STATUS_CACHE.move_to_end(key)
        return deepcopy(entry[1])


def _store_repository_status(repository: str, result: dict[str, Any], now: float) -> None:
    """Cache bounded status projections by repository and observed default branch."""
    branch_value = result.get("default_branch")
    branch = branch_value if isinstance(branch_value, str) else ""
    ttl = (
        STATUS_CACHE_FAILURE_TTL_SECONDS
        if result.get("status") == "unknown"
        else STATUS_CACHE_TTL_SECONDS
    )
    expires_at = now + ttl
    key = (repository, branch)
    with _STATUS_CACHE_LOCK:
        previous = _STATUS_CACHE_INDEX.get(repository)
        if previous is not None:
            _STATUS_CACHE.pop((repository, previous[0]), None)
        _STATUS_CACHE[key] = (expires_at, deepcopy(result))
        _STATUS_CACHE.move_to_end(key)
        _STATUS_CACHE_INDEX[repository] = (branch, expires_at)
        while len(_STATUS_CACHE) > STATUS_CACHE_MAX_ENTRIES:
            evicted_key, _ = _STATUS_CACHE.popitem(last=False)
            evicted_repository = evicted_key[0]
            indexed = _STATUS_CACHE_INDEX.get(evicted_repository)
            if indexed is not None and indexed[0] == evicted_key[1]:
                _STATUS_CACHE_INDEX.pop(evicted_repository, None)


def _clear_status_cache() -> None:
    """Clear process-local status cache; intended for deterministic tests."""
    with _STATUS_CACHE_LOCK:
        _STATUS_CACHE.clear()
        _STATUS_CACHE_INDEX.clear()


def get_repository_status(repository: str) -> dict[str, Any]:
    """Read cached public GitHub status; failures remain short-lived unknowns."""
    now = time.monotonic()
    cached = _cached_repository_status(repository, now)
    if cached is not None:
        return cached
    result = GitHubStatusClient().read_repository_status(repository)
    _store_repository_status(repository, result, time.monotonic())
    return deepcopy(result)
