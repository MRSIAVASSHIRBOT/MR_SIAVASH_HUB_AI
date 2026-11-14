"""Read-only discovery adapters for allow-listed public discussion APIs.

Search results are candidates for human review, not verified demand or endorsements.
Only fixed provider endpoints are contacted; user-supplied URLs are never fetched.
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from datetime import UTC, datetime
from urllib.parse import urlsplit

import httpx


class ResearchDiscoveryError(RuntimeError):
    """A bounded public-source discovery request could not be completed."""

    def __init__(self, message: str, status_code: int = 502) -> None:
        super().__init__(message)
        self.status_code = status_code


class _DiscoveryLimiter:
    """Small in-process per-owner request budget and identical-query cooldown."""

    def __init__(self, max_requests: int = 6, window_seconds: int = 60) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: dict[str, deque[float]] = defaultdict(deque)
        self._last_query: dict[tuple[str, str], float] = {}
        self._lock = threading.Lock()

    def check(self, owner_id: str, query_key: str) -> None:
        now = time.monotonic()
        with self._lock:
            requests = self._requests[owner_id]
            cutoff = now - self.window_seconds
            while requests and requests[0] <= cutoff:
                requests.popleft()
            last = self._last_query.get((owner_id, query_key))
            if last is not None and now - last < self.window_seconds:
                raise ResearchDiscoveryError(
                    "The same source query can be repeated once per minute.", 429
                )
            if len(requests) >= self.max_requests:
                raise ResearchDiscoveryError(
                    "Research discovery request limit reached; retry in a minute.", 429
                )
            requests.append(now)
            self._last_query[(owner_id, query_key)] = now


_LIMITER = _DiscoveryLimiter()
_MAX_RESPONSE_BYTES = 1_000_000
_STACK_SITES = {
    "stackoverflow": "stackoverflow.com",
    "superuser": "superuser.com",
    "webapps": "webapps.stackexchange.com",
    "askubuntu": "askubuntu.com",
    "serverfault": "serverfault.com",
    "workplace": "workplace.stackexchange.com",
    "academia": "academia.stackexchange.com",
    "writers": "writers.stackexchange.com",
}


def _bounded_json(url: str, params: dict[str, str | int]) -> dict[str, object]:
    try:
        with httpx.Client(
            timeout=httpx.Timeout(6.0, connect=3.0),
            follow_redirects=False,
            trust_env=False,
            headers={"Accept": "application/json", "User-Agent": "MR-SIAVASH-HUB-AI-Research/1.0"},
        ) as client:
            with client.stream("GET", url, params=params) as response:
                if response.status_code == 429:
                    raise ResearchDiscoveryError("The public source rate limit was reached.", 429)
                if response.status_code != 200:
                    raise ResearchDiscoveryError("The public source returned an unavailable response.", 502)
                declared_size = response.headers.get("content-length")
                if declared_size and int(declared_size) > _MAX_RESPONSE_BYTES:
                    raise ResearchDiscoveryError("The public source response exceeded the size limit.", 502)
                chunks: list[bytes] = []
                size = 0
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > _MAX_RESPONSE_BYTES:
                        raise ResearchDiscoveryError("The public source response exceeded the size limit.", 502)
                    chunks.append(chunk)
        import json

        payload = json.loads(b"".join(chunks))
        if not isinstance(payload, dict):
            raise ResearchDiscoveryError("The public source returned an invalid response.", 502)
        return payload
    except ResearchDiscoveryError:
        raise
    except (httpx.HTTPError, ValueError, TypeError) as exc:
        raise ResearchDiscoveryError("The public source could not be reached safely.", 502) from exc


def discover_public_needs(
    *, owner_user_id: str, source: str, query: str, limit: int = 10, site: str = "superuser"
) -> dict[str, object]:
    """Search Hacker News or a fixed Stack Exchange site; never fetch result URLs."""
    normalized_query = " ".join(query.split())
    if not normalized_query or len(normalized_query) > 160:
        raise ResearchDiscoveryError("Query must contain 1 to 160 characters.", 422)
    bounded_limit = max(1, min(int(limit), 20))
    if source not in {"hacker_news", "stack_exchange"}:
        raise ResearchDiscoveryError("Unsupported public research source.", 422)
    if source == "stack_exchange" and site not in _STACK_SITES:
        raise ResearchDiscoveryError("Unsupported Stack Exchange site.", 422)

    query_key = f"{source}:{site if source == 'stack_exchange' else ''}:{normalized_query.casefold()}"
    _LIMITER.check(owner_user_id, query_key)

    captured_at = datetime.now(UTC).isoformat()
    if source == "hacker_news":
        payload = _bounded_json(
            "https://hn.algolia.com/api/v1/search",
            {"query": normalized_query, "tags": "story", "hitsPerPage": bounded_limit},
        )
        raw_items = payload.get("hits", [])
        items: list[dict[str, object]] = []
        if isinstance(raw_items, list):
            for hit in raw_items:
                if not isinstance(hit, dict):
                    continue
                item_id = hit.get("objectID")
                title = hit.get("title")
                if not isinstance(item_id, str) or not item_id.isdigit() or not isinstance(title, str) or not title.strip():
                    continue
                items.append({
                    "source_type": "public_discussion",
                    "source_label": "Hacker News",
                    "title": title[:300],
                    "source_url": f"https://news.ycombinator.com/item?id={item_id}",
                    "published_at": hit.get("created_at") if isinstance(hit.get("created_at"), str) else None,
                    "score": hit.get("points") if isinstance(hit.get("points"), int) else None,
                    "discussion_count": hit.get("num_comments") if isinstance(hit.get("num_comments"), int) else None,
                    "summary": "Candidate discussion; open the source and review context before recording evidence.",
                })
        source_label = "Hacker News (Algolia public search API)"
    else:
        payload = _bounded_json(
            "https://api.stackexchange.com/2.3/search/advanced",
            {
                "order": "desc",
                "sort": "relevance",
                "site": site,
                "q": normalized_query,
                "pagesize": bounded_limit,
            },
        )
        raw_items = payload.get("items", [])
        expected_host = _STACK_SITES[site]
        items = []
        if isinstance(raw_items, list):
            for hit in raw_items:
                if not isinstance(hit, dict):
                    continue
                title, link = hit.get("title"), hit.get("link")
                if not isinstance(title, str) or not isinstance(link, str):
                    continue
                parsed = urlsplit(link)
                if parsed.scheme != "https" or parsed.hostname != expected_host:
                    continue
                created = hit.get("creation_date")
                published_at = (
                    datetime.fromtimestamp(created, UTC).isoformat()
                    if isinstance(created, int) and not isinstance(created, bool)
                    else None
                )
                tags = hit.get("tags", [])
                items.append({
                    "source_type": "community_forum",
                    "source_label": f"Stack Exchange / {site}",
                    "title": title[:300],
                    "source_url": link,
                    "published_at": published_at,
                    "score": hit.get("score") if isinstance(hit.get("score"), int) else None,
                    "discussion_count": hit.get("answer_count") if isinstance(hit.get("answer_count"), int) else None,
                    "tags": [tag[:50] for tag in tags[:12] if isinstance(tag, str)] if isinstance(tags, list) else [],
                    "summary": "Candidate question; review its answers, context, and date before recording evidence.",
                })
        source_label = f"Stack Exchange / {site}"

    return {
        "source": source,
        "source_label": source_label,
        "query": normalized_query,
        "captured_at": captured_at,
        "items": items[:bounded_limit],
        "count": len(items[:bounded_limit]),
        "review_required": True,
        "automatically_saved_as_evidence": False,
        "limitations": [
            "Search results are discovery leads, not verified or representative evidence.",
            "No result page is fetched; private communities and personal profiles are not accessed.",
            "Review source date, context, terms, and independence before attaching evidence.",
        ],
    }
