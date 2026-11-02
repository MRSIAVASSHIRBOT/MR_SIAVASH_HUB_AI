"""Safe, optional health bridge for a separately managed assistant gateway."""

from __future__ import annotations

import ipaddress
import re
from urllib.parse import urlsplit, urlunsplit

import httpx
from fastapi import APIRouter, Depends

from mrhub.api.dependencies import require_user
from mrhub.config import get_settings

router = APIRouter(
    prefix="/integrations/assistant-gateway",
    tags=["integrations"],
    dependencies=[Depends(require_user)],
)


def validate_loopback_base_url(value: str | None) -> str | None:
    """Accept only explicit HTTP(S) URLs whose host is a literal loopback IP."""
    if not value:
        return None
    try:
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"}:
            return None
        if not parsed.hostname or parsed.username or parsed.password:
            return None
        if parsed.query or parsed.fragment:
            return None
        if parsed.port is not None and not (1 <= parsed.port <= 65535):
            return None
        address = ipaddress.ip_address(parsed.hostname)
        if not address.is_loopback:
            return None
    except (ValueError, TypeError):
        return None
    path = parsed.path.rstrip("/")
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


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


@router.get("/status", summary="Check optional assistant gateway connectivity")
async def assistant_gateway_status() -> dict[str, object]:
    """Probe a configured loopback gateway without exposing its response body."""
    settings = get_settings()
    if not settings.assistant_gateway_enabled:
        return {"status": "disabled", "configured": bool(settings.assistant_gateway_base_url)}

    base_url = validate_loopback_base_url(settings.assistant_gateway_base_url)
    health_path = validate_health_path(settings.assistant_gateway_health_path)
    if base_url is None or health_path is None:
        return {"status": "invalid_configuration", "configured": False}

    url = f"{base_url}{health_path}"
    try:
        async with (
            httpx.AsyncClient(
                timeout=settings.assistant_gateway_timeout_seconds,
                follow_redirects=False,
                trust_env=False,
            ) as client,
            client.stream("GET", url, headers={"Accept": "application/json"}) as response,
        ):
                if response.is_redirect:
                    return {"status": "rejected_redirect", "configured": True}
                if response.status_code < 200 or response.status_code >= 300:
                    return {"status": "unreachable", "configured": True, "http_status": response.status_code}
                received = 0
                async for chunk in response.aiter_bytes(chunk_size=1024):
                    received += len(chunk)
                    if received > settings.assistant_gateway_max_response_bytes:
                        return {"status": "response_too_large", "configured": True}
                return {"status": "reachable", "configured": True, "http_status": response.status_code}
    except (httpx.HTTPError, OSError, ValueError):
        return {"status": "unreachable", "configured": True}
