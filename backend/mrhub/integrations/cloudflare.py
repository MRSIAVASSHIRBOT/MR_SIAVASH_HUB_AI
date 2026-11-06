"""Typed, read-only Cloudflare API adapter with strict scope and redaction.

This module deliberately exposes no arbitrary URL, method, header, or body input.
It is optional: callers instantiate it only when a read-only API token is configured.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field

CLOUDFLARE_API_BASE = "https://api.cloudflare.com/client/v4"
MAX_RESPONSE_BYTES = 1_048_576
MAX_PAGES = 20
PAGE_SIZE = 50
REQUEST_TIMEOUT_SECONDS = 8.0
ACCOUNT_ID_PATTERN = re.compile(r"^[a-f0-9]{32}$")
RESOURCE_NAME_PATTERN = re.compile(r"^[a-z0-9_][a-z0-9_-]{0,62}$")


class CloudflareAdapterError(RuntimeError):
    """Sanitized provider error; never includes response bodies or credentials."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class WorkerSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1, max_length=128)
    etag: str | None = Field(default=None, max_length=128)
    created_on: str | None = Field(default=None, max_length=64)
    modified_on: str | None = Field(default=None, max_length=64)


class WorkerRoute(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1, max_length=128)
    pattern: str = Field(min_length=1, max_length=253)
    script: str | None = Field(default=None, max_length=63)
    zone_id: str | None = Field(default=None, max_length=32)


class BindingMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1, max_length=128)
    type: str = Field(min_length=1, max_length=64)


class WorkerSettingsSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    compatibility_date: str | None = Field(default=None, max_length=32)
    usage_model: str | None = Field(default=None, max_length=32)
    bindings: list[BindingMetadata] = Field(default_factory=list, max_length=100)


class D1DatabaseSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    uuid: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=128)
    created_at: str | None = Field(default=None, max_length=64)


class CloudflareReadOnlyClient:
    """Allowlisted Cloudflare metadata reader.

    Account and zone identifiers are supplied by trusted application config.
    All provider requests use a fixed origin and fixed endpoint templates.
    """

    def __init__(
        self,
        *,
        api_token: str,
        allowed_account_ids: frozenset[str] | set[str],
        allowed_zone_ids: frozenset[str] | set[str] = frozenset(),
        timeout_seconds: float = REQUEST_TIMEOUT_SECONDS,
        max_response_bytes: int = MAX_RESPONSE_BYTES,
    ) -> None:
        if not isinstance(api_token, str) or not api_token.strip():
            raise ValueError("Cloudflare API token is required")
        if not 0 < timeout_seconds <= REQUEST_TIMEOUT_SECONDS:
            raise ValueError("Invalid Cloudflare timeout")
        if not 1 <= max_response_bytes <= MAX_RESPONSE_BYTES:
            raise ValueError("Invalid Cloudflare response limit")

        accounts = frozenset(allowed_account_ids)
        zones = frozenset(allowed_zone_ids)
        if not accounts or any(not ACCOUNT_ID_PATTERN.fullmatch(v) for v in accounts):
            raise ValueError("At least one valid account allowlist entry is required")
        if any(not ACCOUNT_ID_PATTERN.fullmatch(v) for v in zones):
            raise ValueError("Invalid zone allowlist entry")

        self._token = api_token.strip()
        self._accounts = accounts
        self._zones = zones
        self._timeout = timeout_seconds
        self._max_response_bytes = max_response_bytes

    def _account_path(self, account_id: str, suffix: str) -> str:
        if account_id not in self._accounts:
            raise CloudflareAdapterError("account_not_allowlisted")
        return f"/accounts/{account_id}/{suffix}"

    def _zone_path(self, zone_id: str, suffix: str) -> str:
        if zone_id not in self._zones:
            raise CloudflareAdapterError("zone_not_allowlisted")
        return f"/zones/{zone_id}/{suffix}"

    async def _get_json(
        self, path: str, params: Mapping[str, str | int] | None = None
    ) -> dict[str, Any]:
        url = f"{CLOUDFLARE_API_BASE}{path}"
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout, follow_redirects=False, trust_env=False
            ) as client, client.stream(
                "GET",
                url,
                params=params,
                headers={
                    "Authorization": f"Bearer {self._token}",
                    "Accept": "application/json",
                },
            ) as response:
                if response.is_redirect:
                    raise CloudflareAdapterError("provider_redirect_rejected")
                if not 200 <= response.status_code < 300:
                    raise CloudflareAdapterError("provider_http_error")
                body = bytearray()
                async for chunk in response.aiter_bytes(
                    chunk_size=min(8192, self._max_response_bytes + 1)
                ):
                    body.extend(chunk)
                    if len(body) > self._max_response_bytes:
                        raise CloudflareAdapterError("provider_response_too_large")
            try:
                payload = json.loads(body)
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise CloudflareAdapterError("provider_invalid_json") from exc
            if not isinstance(payload, dict) or payload.get("success") is not True:
                raise CloudflareAdapterError("provider_api_error")
            result = payload.get("result")
            if not isinstance(result, (dict, list)):
                raise CloudflareAdapterError("provider_invalid_result")
            return payload
        except CloudflareAdapterError:
            raise
        except httpx.TimeoutException as exc:
            raise CloudflareAdapterError("provider_timeout") from exc
        except (httpx.HTTPError, OSError, ValueError) as exc:
            raise CloudflareAdapterError("provider_unavailable") from exc

    async def _list_pages(self, path: str) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for page in range(1, MAX_PAGES + 1):
            payload = await self._get_json(
                path, {"page": page, "per_page": PAGE_SIZE}
            )
            result = payload["result"]
            if not isinstance(result, list):
                raise CloudflareAdapterError("provider_invalid_result")
            if any(not isinstance(item, dict) for item in result):
                raise CloudflareAdapterError("provider_invalid_item")
            items.extend(result)
            info = payload.get("result_info")
            total_pages = info.get("total_pages") if isinstance(info, dict) else None
            if isinstance(total_pages, int) and page >= total_pages:
                return items
            if total_pages is None and len(result) < PAGE_SIZE:
                return items
        raise CloudflareAdapterError("provider_pagination_limit")

    async def list_workers(self, account_id: str) -> list[WorkerSummary]:
        path = self._account_path(account_id, "workers/scripts")
        records = await self._list_pages(path)
        output: list[WorkerSummary] = []
        for item in records:
            worker_id = item.get("id")
            if not isinstance(worker_id, str) or not RESOURCE_NAME_PATTERN.fullmatch(worker_id):
                continue
            output.append(
                WorkerSummary(
                    id=worker_id,
                    etag=item.get("etag") if isinstance(item.get("etag"), str) else None,
                    created_on=item.get("created_on") if isinstance(item.get("created_on"), str) else None,
                    modified_on=item.get("modified_on") if isinstance(item.get("modified_on"), str) else None,
                )
            )
        return output

    async def list_worker_routes(self, zone_id: str) -> list[WorkerRoute]:
        path = self._zone_path(zone_id, "workers/routes")
        records = await self._list_pages(path)
        output: list[WorkerRoute] = []
        for item in records:
            route_id, pattern = item.get("id"), item.get("pattern")
            if not isinstance(route_id, str) or not isinstance(pattern, str):
                continue
            output.append(
                WorkerRoute(
                    id=route_id,
                    pattern=pattern,
                    script=item.get("script") if isinstance(item.get("script"), str) else None,
                    zone_id=item.get("zone_id") if isinstance(item.get("zone_id"), str) else None,
                )
            )
        return output

    async def get_worker_settings(
        self, account_id: str, script_name: str
    ) -> WorkerSettingsSummary:
        if not RESOURCE_NAME_PATTERN.fullmatch(script_name):
            raise CloudflareAdapterError("invalid_worker_name")
        path = self._account_path(
            account_id, f"workers/scripts/{script_name}/settings"
        )
        payload = await self._get_json(path)
        result = payload["result"]
        if not isinstance(result, dict):
            raise CloudflareAdapterError("provider_invalid_result")

        # Intentionally project only non-secret metadata. Never serialize binding
        # values, including plain_text values, even if the provider returns them.
        safe_bindings: list[BindingMetadata] = []
        raw_bindings = result.get("bindings", [])
        if isinstance(raw_bindings, list):
            for binding in raw_bindings[:100]:
                if not isinstance(binding, dict):
                    continue
                name, kind = binding.get("name"), binding.get("type")
                if isinstance(name, str) and isinstance(kind, str):
                    safe_bindings.append(BindingMetadata(name=name, type=kind))

        return WorkerSettingsSummary(
            compatibility_date=(
                result.get("compatibility_date")
                if isinstance(result.get("compatibility_date"), str)
                else None
            ),
            usage_model=(
                result.get("usage_model")
                if isinstance(result.get("usage_model"), str)
                else None
            ),
            bindings=safe_bindings,
        )

    async def list_d1_databases(self, account_id: str) -> list[D1DatabaseSummary]:
        path = self._account_path(account_id, "d1/database")
        records = await self._list_pages(path)
        output: list[D1DatabaseSummary] = []
        for item in records:
            uuid, name = item.get("uuid"), item.get("name")
            if not isinstance(uuid, str) or not isinstance(name, str):
                continue
            output.append(
                D1DatabaseSummary(
                    uuid=uuid,
                    name=name,
                    created_at=item.get("created_at")
                    if isinstance(item.get("created_at"), str)
                    else None,
                )
            )
        return output
