"""Shared bounded health probing for optional local integrations."""

from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit

import ipaddress
import re

import httpx


INTEGRATION_CONTRACT_VERSION = "1.0"


def _valid_local_path(value: str, *, allow_root: bool = True) -> bool:
    """Accept plain URL path segments only; reject encoded or ambiguous separators."""
    if not value.startswith("/") or value.startswith("//"):
        return False
    if not re.fullmatch(r"/[A-Za-z0-9._~/-]*", value):
        return False
    if not allow_root and value == "/":
        return False
    parts = value.split("/")[1:]
    return all(part not in {"", ".", ".."} for part in parts) or (
        allow_root and value == "/"
    )


def validate_loopback_base_url(value: str | None) -> str | None:
    """Accept HTTP(S) URLs whose host is a literal loopback IP and path is unambiguous."""
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
        if parsed.path and not _valid_local_path(parsed.path):
            return None
    except (ValueError, TypeError):
        return None
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", ""))


def validate_health_path(value: str) -> str | None:
    """Reject absolute URLs, traversal, encoded separators, and ambiguous paths."""
    if not value:
        return None
    parsed = urlsplit(value)
    if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment:
        return None
    if not _valid_local_path(parsed.path):
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
        return {
            "contract_version": INTEGRATION_CONTRACT_VERSION,
            "status": "invalid_configuration",
            "configured": False,
        }
    try:
        async with httpx.AsyncClient(
            timeout=timeout_seconds, follow_redirects=False, trust_env=False
        ) as client, client.stream(
            "GET", f"{base}{path}", headers={"Accept": "application/json"}
        ) as response:
            if response.is_redirect:
                return {
                    "contract_version": INTEGRATION_CONTRACT_VERSION,
                    "status": "rejected_redirect",
                    "configured": True,
                }
            if not 200 <= response.status_code < 300:
                return {
                    "contract_version": INTEGRATION_CONTRACT_VERSION,
                    "status": "unreachable",
                    "configured": True,
                    "http_status": response.status_code,
                }
            if not 1 <= max_response_bytes <= 16384:
                return {
                    "contract_version": INTEGRATION_CONTRACT_VERSION,
                    "status": "invalid_configuration",
                    "configured": False,
                }
            received = 0
            while received <= max_response_bytes:
                # Request at most the remaining budget plus one byte. This keeps
                # memory/network consumption bounded even for oversized chunks.
                chunk_size = min(1024, max_response_bytes + 1 - received)
                chunk = await response.aread() if chunk_size <= 0 else None
                if chunk is not None:
                    received += len(chunk)
                    break
                async for part in response.aiter_bytes(chunk_size=chunk_size):
                    received += len(part)
                    break
                else:
                    break
            if received > max_response_bytes:
                return {
                    "contract_version": INTEGRATION_CONTRACT_VERSION,
                    "status": "response_too_large",
                    "configured": True,
                }
            # A single read may not exhaust a response when a transport yields
            # multiple chunks; continue with the remaining byte budget.
            async for chunk in response.aiter_bytes(chunk_size=1024):
                received += len(chunk)
                if received > max_response_bytes:
                    return {
                        "contract_version": INTEGRATION_CONTRACT_VERSION,
                        "status": "response_too_large",
                        "configured": True,
                    }
            return {
                "contract_version": INTEGRATION_CONTRACT_VERSION,
                "status": "reachable",
                "configured": True,
                "http_status": response.status_code,
            }
    except (httpx.HTTPError, OSError, ValueError):
        return {
            "contract_version": INTEGRATION_CONTRACT_VERSION,
            "status": "unreachable",
            "configured": True,
        }
