"""Read-only, bounded SiaCode health preflight.

This module never launches processes, creates tunnels, downloads models, or submits
coding work. It only probes an explicitly configured loopback health endpoint.
"""
from __future__ import annotations

import json
from urllib.parse import urlsplit, urlunsplit

import httpx

from mrhub.config import Settings, get_settings


class SiaCodePreflight:
    """Fail-closed health probe for an externally managed local SiaCode bridge."""

    MAX_RESPONSE_BYTES = 16_384
    _LOOPBACK_NAMES = frozenset({"127.0.0.1", "::1", "localhost"})

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        client: httpx.Client | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._client = client

    @staticmethod
    def _health_url(value: str | None) -> str | None:
        if not value or not value.strip():
            return None
        try:
            parsed = urlsplit(value.strip())
            port = parsed.port
        except ValueError:
            return None
        if (
            parsed.scheme not in {"http", "https"}
            or parsed.hostname not in SiaCodePreflight._LOOPBACK_NAMES
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            return None

        # Remote tunnels and arbitrary hosts require a separately reviewed stage.
        netloc = f"[{parsed.hostname}]" if ":" in parsed.hostname else parsed.hostname
        if port is not None:
            netloc += f":{port}"
        base_path = parsed.path.rstrip("/")
        return urlunsplit((parsed.scheme, netloc, f"{base_path}/health", "", ""))

    def check(self) -> dict[str, str | bool]:
        """Return stable state/reason fields, never URLs, response bodies, or secrets."""
        if not self._settings.siacode_enabled:
            return {"state": "disabled", "ready": False, "reason_code": "disabled"}

        url = self._health_url(self._settings.siacode_base_url)
        if url is None:
            return {
                "state": "unconfigured",
                "ready": False,
                "reason_code": "invalid_or_missing_config",
            }

        client = self._client
        owns_client = client is None
        if client is None:
            client = httpx.Client(
                timeout=self._settings.siacode_timeout_seconds,
                follow_redirects=False,
                trust_env=False,
            )
        try:
            with client.stream("GET", url, follow_redirects=False) as response:
                if 300 <= response.status_code < 400:
                    return {
                        "state": "failed",
                        "ready": False,
                        "reason_code": "redirect_rejected",
                    }
                if response.status_code != 200:
                    return {
                        "state": "unavailable",
                        "ready": False,
                        "reason_code": "health_status_not_ok",
                    }

                body = bytearray()
                limit = min(
                    self._settings.siacode_max_response_bytes,
                    self.MAX_RESPONSE_BYTES,
                )
                for chunk in response.iter_bytes():
                    body.extend(chunk)
                    if len(body) > limit:
                        return {
                            "state": "failed",
                            "ready": False,
                            "reason_code": "response_too_large",
                        }
                try:
                    payload = json.loads(body)
                except (ValueError, UnicodeDecodeError):
                    return {
                        "state": "failed",
                        "ready": False,
                        "reason_code": "invalid_health_payload",
                    }
                if not isinstance(payload, dict):
                    return {
                        "state": "failed",
                        "ready": False,
                        "reason_code": "invalid_health_payload",
                    }
                return {"state": "ready", "ready": True, "reason_code": "health_ok"}
        except httpx.TimeoutException:
            return {"state": "unavailable", "ready": False, "reason_code": "timeout"}
        except httpx.HTTPError:
            return {
                "state": "unavailable",
                "ready": False,
                "reason_code": "endpoint_unreachable",
            }
        finally:
            if owns_client:
                client.close()
