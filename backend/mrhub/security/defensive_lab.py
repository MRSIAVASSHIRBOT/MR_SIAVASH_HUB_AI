"""Offline defensive configuration review with explicit authorization scope."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ScopeValidationError(ValueError):
    """Raised when a defensive review has no valid authorization boundary."""


class DefensiveReviewScope(BaseModel):
    """Explicit scope record for local/read-only review; it does not authorize active testing."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    authorization_reference: str = Field(min_length=3, max_length=200)
    authorized_assets: tuple[str, ...] = Field(min_length=1, max_length=100)
    expires_at: datetime
    review_mode: Literal["offline_static_only"] = "offline_static_only"

    @field_validator("authorization_reference")
    @classmethod
    def authorization_must_be_explicit(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("authorization reference must not be blank")
        return value

    @field_validator("authorized_assets")
    @classmethod
    def assets_must_be_unique_and_nonblank(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(item.strip() for item in value)
        if any(not item for item in normalized):
            raise ValueError("authorized assets must not be blank")
        if len(set(normalized)) != len(normalized):
            raise ValueError("authorized assets must be unique")
        return normalized

    def assert_current(self, now: datetime | None = None) -> None:
        current = now or datetime.now(UTC)
        if current.tzinfo is None or current.utcoffset() is None:
            raise ScopeValidationError("Current time must be timezone-aware")
        if self.expires_at.tzinfo is None or self.expires_at.utcoffset() is None:
            raise ScopeValidationError("Authorization expiry must be timezone-aware")
        if self.expires_at.astimezone(UTC) <= current.astimezone(UTC):
            raise ScopeValidationError("Defensive review authorization has expired")


_RULES: tuple[tuple[str, str, str, re.Pattern[str]], ...] = (
    (
        "CFG001", "high", "Debug mode appears enabled.",
        re.compile(r"(?im)^\s*(?:debug|debug_mode)\s*[:=]\s*(?:true|1|yes)\s*(?:#.*)?$"),
    ),
    (
        "CFG002", "high", "Service appears configured to bind to every network interface.",
        re.compile(r"(?im)^\s*(?:host|bind_address)\s*[:=]\s*['\"]?0\.0\.0\.0['\"]?\s*(?:#.*)?$"),
    ),
    (
        "CFG003", "high", "TLS certificate verification appears disabled.",
        re.compile(r"(?im)^\s*(?:verify|ssl_verify|tls_verify)\s*[:=]\s*(?:false|0|no)\s*(?:#.*)?$"),
    ),
    (
        "CFG004", "medium", "Wildcard cross-origin policy appears configured.",
        re.compile(r"(?i)(?:allow_origins|allowed_origins|cors_origins)\s*[:=].*(?:\*|\[['\"]\*['\"]\])"),
    ),
    (
        "CFG005", "medium", "Secure cookie flag appears disabled.",
        re.compile(r"(?im)^\s*(?:session_cookie_secure|cookie_secure|secure_cookies)\s*[:=]\s*(?:false|0|no)\s*(?:#.*)?$"),
    ),
    (
        "CFG006", "medium", "HttpOnly cookie flag appears disabled.",
        re.compile(r"(?im)^\s*(?:session_cookie_httponly|cookie_httponly|httponly)\s*[:=]\s*(?:false|0|no)\s*(?:#.*)?$"),
    ),
)


def audit_configuration_text(text: str, *, filename: str = "config") -> dict[str, object]:
    """Report risky configuration patterns by line without echoing configuration values."""
    if len(text) > 1_000_000:
        raise ValueError("Configuration text exceeds the 1 MB review limit")
    findings: list[dict[str, object]] = []
    lines = text.splitlines()
    for line_number, line in enumerate(lines, start=1):
        for rule_id, severity, message, pattern in _RULES:
            if pattern.search(line):
                findings.append({
                    "rule_id": rule_id,
                    "severity": severity,
                    "file": filename[:255],
                    "line": line_number,
                    "message": message,
                })
    return {
        "mode": "offline_defensive_configuration_review",
        "lines_reviewed": len(lines),
        "findings": findings,
        "configuration_values_included": False,
        "network_requests_made": False,
        "targets_modified": False,
    }
