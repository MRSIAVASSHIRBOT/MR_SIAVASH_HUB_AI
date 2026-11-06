"""Typed Hub-side client for the isolated Cloudflare Workers gateway.

The Hub never holds a Cloudflare provider token. This module accepts only the
separate gateway service credential and exposes fixed, read-only operations.
"""

from __future__ import annotations

import ipaddress
import json
import re
import time
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel, ConfigDict, Field, SecretStr

from mrhub.config import Settings

MAX_RESPONSE_BYTES = 1_048_576
MAX_LIST_ITEMS = 1_000
REQUEST_TIMEOUT_SECONDS = 8.0
RESOURCE_NAME_PATTERN = re.compile(r"^[a-z0-9_][a-z0-9_-]{0,62}$")
JSON_CONTENT_TYPE = re.compile(r"^application/(?:json|[a-z0-9.+-]+\+json)(?:\s*;|$)", re.IGNORECASE)


class CloudflareGatewayError(RuntimeError):
    """Sanitized gateway error; never includes response bodies or credentials."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class WorkerSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    id: str = Field(min_length=1, max_length=63)
    etag: str | None = Field(default=None, max_length=128)
    created_on: str | None = Field(default=None, max_length=64)
    modified_on: str | None = Field(default=None, max_length=64)


class WorkerRoute(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    id: str = Field(min_length=1, max_length=128)
    pattern: str = Field(min_length=1, max_length=253)
    script: str | None = Field(default=None, max_length=63)
    zone_id: str | None = Field(default=None, max_length=32)


class BindingMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    name: str = Field(min_length=1, max_length=128)
    type: str = Field(min_length=1, max_length=64)


class WorkerSettingsSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    compatibility_date: str | None = Field(default=None, max_length=32)
    usage_model: str | None = Field(default=None, max_length=32)
    bindings: list[BindingMetadata] = Field(default_factory=list, max_length=100)


class D1DatabaseSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    uuid: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=128)
    created_at: str | None = Field(default=None, max_length=64)


def _validate_gateway_url(value: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > 2_048
    ):
        raise ValueError("Invalid Cloudflare gateway URL")
    try:
        parsed = urlsplit(value)
        host = parsed.hostname
        port = parsed.port
    except ValueError:
        raise ValueError("Invalid Cloudflare gateway URL") from None
    if (
        parsed.scheme != "https"
        or not host
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
        or (port is not None and not 1 <= port <= 65_535)
    ):
        raise ValueError("Invalid Cloudflare gateway URL")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise ValueError("Cloudflare gateway URL must use a public DNS hostname")
    try:
        normalized_host = host.encode("idna").decode("ascii").lower().rstrip(".")
    except UnicodeError:
        raise ValueError("Invalid Cloudflare gateway hostname") from None
    hostname_pattern = (
        r"^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
        r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$"
    )
    if (
        not re.fullmatch(hostname_pattern, normalized_host)
        or normalized_host == "localhost"
        or normalized_host.endswith((".localhost", ".local", ".internal"))
    ):
        raise ValueError("Cloudflare gateway URL must use a public DNS hostname")
    return f"https://{parsed.netloc}".rstrip("/")


class CloudflareGatewayClient:
    """Synchronous, typed client suitable for the existing ToolRegistry contract."""

    def __init__(
        self,
        *,
        gateway_url: str,
        gateway_token: SecretStr,
        timeout_seconds: float = REQUEST_TIMEOUT_SECONDS,
        max_response_bytes: int = MAX_RESPONSE_BYTES,
    ) -> None:
        if not isinstance(gateway_token, SecretStr):
            raise TypeError("Cloudflare gateway token must be SecretStr")
        token = gateway_token.get_secret_value()
        if (
            len(token) < 32
            or len(token) > 512
            or not token.isascii()
            or any(ord(character) < 33 or ord(character) > 126 for character in token)
        ):
            raise ValueError("Invalid Cloudflare gateway token")
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, (int, float))
            or not 0 < timeout_seconds <= REQUEST_TIMEOUT_SECONDS
        ):
            raise ValueError("Invalid Cloudflare gateway timeout")
        if (
            isinstance(max_response_bytes, bool)
            or not isinstance(max_response_bytes, int)
            or not 1 <= max_response_bytes <= MAX_RESPONSE_BYTES
        ):
            raise ValueError("Invalid Cloudflare gateway response limit")

        self._base_url = _validate_gateway_url(gateway_url)
        self._token = token
        self._timeout = float(timeout_seconds)
        self._max_response_bytes = max_response_bytes

    def _get_data(self, path: str) -> Any:
        # Callers pass only module-owned, fixed route templates.
        if not path.startswith("/v1/") or "?" in path or "#" in path:
            raise CloudflareGatewayError("invalid_gateway_operation")
        deadline = time.monotonic() + self._timeout
        try:
            with httpx.Client(
                timeout=self._timeout,
                follow_redirects=False,
                trust_env=False,
            ) as client, client.stream(
                "GET",
                self._base_url + path,
                headers={
                    "Authorization": f"Bearer {self._token}",
                    "Accept": "application/json",
                },
            ) as response:
                if response.is_redirect:
                    raise CloudflareGatewayError("gateway_redirect_rejected")
                if not 200 <= response.status_code < 300:
                    raise CloudflareGatewayError("gateway_http_error")
                content_type = response.headers.get("content-type", "")
                if not JSON_CONTENT_TYPE.match(content_type):
                    raise CloudflareGatewayError("gateway_invalid_content_type")
                declared_length = response.headers.get("content-length")
                if declared_length is not None:
                    try:
                        parsed_length = int(declared_length)
                    except ValueError:
                        raise CloudflareGatewayError("gateway_invalid_response") from None
                    if parsed_length < 0:
                        raise CloudflareGatewayError("gateway_invalid_response")
                    if parsed_length > self._max_response_bytes:
                        raise CloudflareGatewayError("gateway_response_too_large")

                body = bytearray()
                for chunk in response.iter_bytes(
                    chunk_size=min(8_192, self._max_response_bytes + 1)
                ):
                    if time.monotonic() > deadline:
                        raise CloudflareGatewayError("gateway_timeout")
                    body.extend(chunk)
                    if len(body) > self._max_response_bytes:
                        raise CloudflareGatewayError("gateway_response_too_large")
        except CloudflareGatewayError:
            raise
        except httpx.TimeoutException:
            raise CloudflareGatewayError("gateway_timeout") from None
        except (httpx.HTTPError, OSError, ValueError):
            raise CloudflareGatewayError("gateway_unavailable") from None

        try:
            envelope = json.loads(body)
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise CloudflareGatewayError("gateway_invalid_json") from None
        if (
            not isinstance(envelope, dict)
            or envelope.get("ok") is not True
            or "data" not in envelope
        ):
            raise CloudflareGatewayError("gateway_invalid_envelope")
        return envelope["data"]

    @staticmethod
    def _list_data(value: Any) -> list[Mapping[str, Any]]:
        if not isinstance(value, list):
            raise CloudflareGatewayError("gateway_invalid_result")
        if len(value) > MAX_LIST_ITEMS:
            raise CloudflareGatewayError("gateway_item_limit")
        if any(not isinstance(item, dict) for item in value):
            raise CloudflareGatewayError("gateway_invalid_item")
        return value

    def list_workers(self) -> list[WorkerSummary]:
        records = self._list_data(self._get_data("/v1/workers"))
        output: list[WorkerSummary] = []
        for item in records:
            worker_id = item.get("id")
            if not isinstance(worker_id, str) or not RESOURCE_NAME_PATTERN.fullmatch(worker_id):
                continue
            output.append(WorkerSummary.model_validate(item))
        return output

    def list_worker_routes(self) -> list[WorkerRoute]:
        records = self._list_data(self._get_data("/v1/worker-routes"))
        return [WorkerRoute.model_validate(item) for item in records]

    def list_d1_databases(self) -> list[D1DatabaseSummary]:
        records = self._list_data(self._get_data("/v1/d1-databases"))
        return [D1DatabaseSummary.model_validate(item) for item in records]

    def get_worker_settings(self, script_name: str) -> WorkerSettingsSummary:
        if (
            not isinstance(script_name, str)
            or not RESOURCE_NAME_PATTERN.fullmatch(script_name)
        ):
            raise CloudflareGatewayError("invalid_worker_name")
        data = self._get_data(f"/v1/workers/{script_name}/settings")
        if not isinstance(data, dict):
            raise CloudflareGatewayError("gateway_invalid_result")
        return WorkerSettingsSummary.model_validate(data)


def build_cloudflare_gateway_client(settings: Settings) -> CloudflareGatewayClient | None:
    """Return None when disabled; fail closed for incomplete enabled configuration."""
    if not settings.cloudflare_gateway_enabled:
        return None
    if not settings.cloudflare_gateway_base_url or settings.cloudflare_gateway_token is None:
        raise CloudflareGatewayError("gateway_not_configured")
    return CloudflareGatewayClient(
        gateway_url=settings.cloudflare_gateway_base_url,
        gateway_token=settings.cloudflare_gateway_token,
        timeout_seconds=settings.cloudflare_gateway_timeout_seconds,
        max_response_bytes=settings.cloudflare_gateway_max_response_bytes,
    )
