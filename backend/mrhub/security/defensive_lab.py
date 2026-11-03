"""Offline defensive configuration review with explicit authorization scope."""

from __future__ import annotations

import hashlib
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

    def assert_asset(self, asset: str, now: datetime | None = None) -> str:
        self.assert_current(now)
        normalized = asset.strip()
        if not normalized or normalized not in self.authorized_assets:
            raise ScopeValidationError("Asset is outside the declared authorization scope")
        return normalized


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


def _validate_filename(filename: str) -> str:
    if (
        not filename
        or len(filename) > 255
        or "/" in filename
        or "\\" in filename
        or filename in {".", ".."}
    ):
        raise ValueError("filename_must_be_a_basename")
    return filename


def _finding(
    rule_id: str,
    severity: str,
    confidence: str,
    filename: str,
    line: int,
    message: str,
    remediation: str,
) -> dict[str, object]:
    return {
        "rule_id": rule_id,
        "severity": severity,
        "confidence": confidence,
        "file": filename,
        "line": line,
        "message": message,
        "remediation": remediation,
    }


def _validated_scope(
    scope: DefensiveReviewScope,
    asset: str,
    now: datetime | None,
) -> str:
    if not isinstance(scope, DefensiveReviewScope):
        raise ScopeValidationError("An explicit defensive review scope is required")
    return scope.assert_asset(asset, now)


def audit_configuration_text(
    text: str,
    *,
    scope: DefensiveReviewScope,
    asset: str,
    filename: str = "config",
    now: datetime | None = None,
) -> dict[str, object]:
    """Review caller-supplied config text under a current, exact asset authorization."""
    authorized_asset = _validated_scope(scope, asset, now)
    safe_filename = _validate_filename(filename)
    if not isinstance(text, str) or len(text) > 1_000_000:
        raise ValueError("Configuration text exceeds the 1 MB review limit")
    findings: list[dict[str, object]] = []
    lines = text.splitlines()
    for line_number, line in enumerate(lines, start=1):
        for rule_id, severity, message, pattern in _RULES:
            if pattern.search(line):
                confidence, remediation = {
                    "CFG001": (
                        "high",
                        "Disable debug mode outside local development and verify deployment settings.",
                    ),
                    "CFG002": (
                        "high",
                        "Bind to loopback or an explicitly approved interface; do not expose all interfaces by default.",
                    ),
                    "CFG003": (
                        "high",
                        "Enable certificate verification and configure a trusted CA bundle.",
                    ),
                    "CFG004": (
                        "medium",
                        "Replace wildcard CORS origins with the exact trusted application origins.",
                    ),
                    "CFG005": (
                        "medium",
                        "Enable Secure cookies and serve session cookies only over HTTPS.",
                    ),
                    "CFG006": (
                        "medium",
                        "Enable HttpOnly on session cookies to reduce script access to session tokens.",
                    ),
                }[rule_id]
                findings.append(_finding(
                    rule_id,
                    severity,
                    confidence,
                    safe_filename,
                    line_number,
                    message,
                    remediation,
                ))
    return {
        "mode": "offline_defensive_configuration_review",
        "asset": authorized_asset,
        "authorization_reference": scope.authorization_reference,
        "authorization_expires_at": scope.expires_at.astimezone(UTC).isoformat(),
        "scope_validated": True,
        "lines_reviewed": len(lines),
        "findings": findings,
        "configuration_values_included": False,
        "network_requests_made": False,
        "targets_modified": False,
    }


_REQUIREMENT_RE = re.compile(
    r"^([A-Za-z0-9][A-Za-z0-9._-]*)(?:\\[[^\\]]+\\])?\\s*(.*)$"
)


def audit_requirements_text(
    text: str,
    *,
    scope: DefensiveReviewScope,
    asset: str,
    filename: str = "requirements.txt",
    now: datetime | None = None,
) -> dict[str, object]:
    """Inventory a requirements-style manifest offline; never installs or resolves packages."""
    authorized_asset = _validated_scope(scope, asset, now)
    safe_filename = _validate_filename(filename)
    if not isinstance(text, str) or len(text) > 1_000_000:
        raise ValueError("Dependency manifest exceeds the 1 MB review limit")

    findings: list[dict[str, object]] = []
    packages_reviewed = 0
    unsupported_directives = 0

    def add(
        rule_id: str,
        severity: str,
        confidence: str,
        line_number: int,
        message: str,
        remediation: str,
    ) -> None:
        findings.append(_finding(
            rule_id,
            severity,
            confidence,
            safe_filename,
            line_number,
            message,
            remediation,
        ))

    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith(("-r ", "--requirement ", "-c ", "--constraint ")):
            unsupported_directives += 1
            add(
                "DEP004",
                "medium",
                "high",
                line_number,
                "Nested requirement or constraint file was not expanded.",
                "Review the referenced file separately under the same explicit scope.",
            )
            continue
        if line.startswith(("-e ", "--editable ")) or line.startswith(
            ("git+", "http://", "https://")
        ):
            packages_reviewed += 1
            add(
                "DEP002",
                "high",
                "high",
                line_number,
                "Direct URL, VCS, or editable dependency requires provenance review.",
                "Prefer a trusted package index and an immutable, reviewed release; do not install this entry during review.",
            )
            continue
        if line.startswith(("--index-url", "--extra-index-url", "--find-links", "--trusted-host")):
            unsupported_directives += 1
            add(
                "DEP005",
                "medium",
                "high",
                line_number,
                "Custom package source or host directive requires manual trust review.",
                "Verify the package source independently; this offline review does not contact it.",
            )
            continue

        match = _REQUIREMENT_RE.match(line)
        if match is None:
            unsupported_directives += 1
            add(
                "DEP006",
                "info",
                "medium",
                line_number,
                "Requirement line uses unsupported syntax and was not interpreted.",
                "Review this line manually; the analyzer deliberately does not evaluate pip options.",
            )
            continue

        packages_reviewed += 1
        specifier = match.group(2).split(";", 1)[0].strip()
        if "@" in specifier:
            add(
                "DEP002",
                "high",
                "high",
                line_number,
                "Direct URL dependency requires provenance review.",
                "Prefer a trusted package index and an immutable, reviewed release.",
            )
        elif not specifier.startswith("==") or specifier.startswith("===") or "*" in specifier:
            add(
                "DEP001",
                "medium",
                "high",
                line_number,
                "Dependency is not pinned to one exact version.",
                "Pin a reviewed exact version and maintain hashes in the deployment lock file.",
            )

    return {
        "mode": "offline_dependency_manifest_review",
        "asset": authorized_asset,
        "authorization_reference": scope.authorization_reference,
        "authorization_expires_at": scope.expires_at.astimezone(UTC).isoformat(),
        "scope_validated": True,
        "manifest_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "packages_reviewed": packages_reviewed,
        "unsupported_directives": unsupported_directives,
        "review_complete": unsupported_directives == 0,
        "findings": findings,
        "vulnerability_database_consulted": False,
        "network_requests_made": False,
        "packages_installed": False,
        "targets_modified": False,
    }
