"""Shared bounded health probing for optional local integrations."""

from __future__ import annotations

import ipaddress
import re
from urllib.parse import urlsplit, urlunsplit

import httpx


def validate_loopback_base_url(value: str | None) -> str | None:
    """Accept only HTTP(S) URLs whose host is a literal loopback IP."""
    if not value:
        return None
    try:
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return None
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            return None
        if parsed.port is not None and not 1 <= parsed.port <= 65535:
            return None
        if not ipaddress.ip_address(parsed.hostname).is_loopback:
            return None
    except (ValueError, TypeError):
        return None
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", ""))


def validate_health_path(value: str) -> str | None:
    """Reject absolute URLs, traversal, query strings, and ambiguous paths."""
    if not value or not value.startswith("/") or value.startswith("//"):
        return None
    parsed = urlsplit(value)
    if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment:
        return None
    if not re.fullmatch(r"/[A-Za-z0-9._~/-]*", parsed.path):
        return None
    if any(part in {".", ".."} for part in parsed.path.split("/")):
        return None
    return parsed.path


async def probe_loopback_service(
    base_url: str | None,
    health_path: str,
    *,
    timeout_seconds: float,
    max_response_bytes: int,
) -> dict[str, object]:
    """Perform a bounded, redirect-free health check and return sanitized status."""
    base = validate_loopback_base_url(base_url)
    path = validate_health_path(health_path)
    if base is None or path is None:
        return {"status": "invalid_configuration", "configured": False}
    try:
        async with httpx.AsyncClient(
            timeout=timeout_seconds, follow_redirects=False, trust_env=False
        ) as client, client.stream(
            "GET", f"{base}{path}", headers={"Accept": "application/json"}
        ) as response:
            if response.is_redirect:
                return {"status": "rejected_redirect", "configured": True}
            if not 200 <= response.status_code < 300:
                return {
                    "status": "unreachable",
                    "configured": True,
                    "http_status": response.status_code,
                }
            received = 0
            async for chunk in response.aiter_bytes(chunk_size=1024):
                received += len(chunk)
                if received > max_response_bytes:
                    return {"status": "response_too_large", "configured": True}
            return {
                "status": "reachable",
                "configured": True,
                "http_status": response.status_code,
            }
    except (httpx.HTTPError, OSError, ValueError):
        return {"status": "unreachable", "configured": True}
