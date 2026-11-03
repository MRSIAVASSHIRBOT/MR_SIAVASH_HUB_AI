"""Offline defensive configuration review with explicit authorization scope."""

import hashlib
import json
import re
from datetime import UTC, datetime, timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

MAX_AUTHORIZATION_LIFETIME_DAYS = 30


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
        if any(not item or len(item) > 200 for item in normalized):
            raise ValueError("authorized assets must be nonblank and at most 200 characters")
        if any(any(ord(character) < 32 for character in item) for item in normalized):
            raise ValueError("authorized assets must not contain control characters")
        if len(set(normalized)) != len(normalized):
            raise ValueError("authorized assets must be unique")
        return normalized

    def assert_current(self, now: datetime | None = None) -> None:
        current = now or datetime.now(UTC)
        if current.tzinfo is None or current.utcoffset() is None:
            raise ScopeValidationError("Current time must be timezone-aware")
        if self.expires_at.tzinfo is None or self.expires_at.utcoffset() is None:
            raise ScopeValidationError("Authorization expiry must be timezone-aware")
        expires_at = self.expires_at.astimezone(UTC)
        current_utc = current.astimezone(UTC)
        if expires_at <= current_utc:
            raise ScopeValidationError("Defensive review authorization has expired")
        if expires_at > current_utc + timedelta(days=MAX_AUTHORIZATION_LIFETIME_DAYS):
            raise ScopeValidationError("Defensive review authorization exceeds the 30-day limit")

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
    r"^([A-Za-z0-9][A-Za-z0-9._-]*)(?:\[[^\]]+\])?\s*(.*)$"
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
        if line.startswith(("-e ", "--editable ", "git+", "http://", "https://")):
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
        version_specifier = specifier.split(maxsplit=1)[0] if specifier else ""
        if "@" in specifier:
            add(
                "DEP002",
                "high",
                "high",
                line_number,
                "Direct URL dependency requires provenance review.",
                "Prefer a trusted package index and an immutable, reviewed release.",
            )
        elif (
            not version_specifier.startswith("==")
            or version_specifier.startswith("===")
            or "*" in version_specifier
            or "," in version_specifier
        ):
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


MAX_STRUCTURED_LOG_LINES = 10_000
MAX_STRUCTURED_LOG_FINDINGS = 200
_AUTH_FAILURE_THRESHOLD = 5


def audit_structured_log_text(
    text: str,
    *,
    scope: DefensiveReviewScope,
    asset: str,
    filename: str = "security-events.jsonl",
    now: datetime | None = None,
) -> dict[str, object]:
    """Review normalized JSONL security events offline without returning identifiers or raw values.

    Supported event_type values:
    - auth.login.failed
    - auth.login.succeeded
    - authorization.role_changed
    - audit.integrity_failed
    - audit.record_deleted

    This is a triage aid for structured logs, not a SIEM, attribution tool, or
    proof that an incident occurred. Unknown schemas and malformed lines are
    counted but never echoed.
    """
    authorized_asset = _validated_scope(scope, asset, now)
    safe_filename = _validate_filename(filename)
    if not isinstance(text, str) or len(text) > 1_000_000:
        raise ValueError("Structured log text exceeds the 1 MB review limit")

    lines = text.splitlines()
    if len(lines) > MAX_STRUCTURED_LOG_LINES:
        raise ValueError("Structured log text exceeds the 10000-line review limit")

    failed_by_actor: dict[str, list[int]] = {}
    successful_by_actor: dict[str, list[int]] = {}
    findings: list[dict[str, object]] = []
    structured_records = 0
    unparsed_lines = 0
    uncorrelated_auth_events = 0

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

    for line_number, raw_line in enumerate(lines, start=1):
        if not raw_line.strip():
            continue
        try:
            record = json.loads(raw_line)
        except (json.JSONDecodeError, TypeError):
            unparsed_lines += 1
            continue
        if not isinstance(record, dict):
            unparsed_lines += 1
            continue

        event_type = record.get("event_type")
        if not isinstance(event_type, str) or not event_type or len(event_type) > 100:
            unparsed_lines += 1
            continue
        structured_records += 1

        actor_id = record.get("actor_id")
        actor_key: str | None = None
        if isinstance(actor_id, str) and actor_id.strip() and len(actor_id) <= 256:
            actor_key = hashlib.sha256(actor_id.strip().encode("utf-8")).hexdigest()

        if event_type in {"auth.login.failed", "auth.login.succeeded"} and actor_key is None:
            uncorrelated_auth_events += 1
        elif event_type == "auth.login.failed" and actor_key is not None:
            failed_by_actor.setdefault(actor_key, []).append(line_number)
        elif event_type == "auth.login.succeeded" and actor_key is not None:
            successful_by_actor.setdefault(actor_key, []).append(line_number)
        elif event_type == "authorization.role_changed":
            add(
                "LOG001",
                "high",
                "medium",
                line_number,
                "A privileged role or authorization assignment changed.",
                "Verify the change against an approved change record and confirm the actor had the required authorization.",
            )
        elif event_type == "audit.integrity_failed":
            add(
                "LOG002",
                "high",
                "high",
                line_number,
                "An audit integrity check reported a failure.",
                "Preserve the original log source and investigate integrity, retention, and access controls before modifying records.",
            )
        elif event_type == "audit.record_deleted":
            add(
                "LOG003",
                "medium",
                "medium",
                line_number,
                "An audit record deletion event was recorded.",
                "Verify that retention policy and an approved administrative action explain the deletion.",
            )

    for actor_key, failure_lines in failed_by_actor.items():
        if len(failure_lines) < _AUTH_FAILURE_THRESHOLD:
            continue
        add(
            "LOG004",
            "medium",
            "medium",
            failure_lines[0],
            f"At least {_AUTH_FAILURE_THRESHOLD} failed authentication events share one pseudonymized actor within this input.",
            "Review the surrounding authentication events and apply the service's normal account-protection procedure if the activity is unexpected.",
        )
        later_successes = [
            line for line in successful_by_actor.get(actor_key, [])
            if line > failure_lines[-1]
        ]
        if later_successes:
            add(
                "LOG005",
                "medium",
                "low",
                later_successes[0],
                "A successful authentication followed repeated failures for the same pseudonymized actor.",
                "Confirm the successful session belongs to the legitimate account owner and review session activity using approved internal procedures.",
            )

    findings.sort(key=lambda item: (int(item["line"]), str(item["rule_id"])))
    findings_truncated = len(findings) > MAX_STRUCTURED_LOG_FINDINGS
    findings = findings[:MAX_STRUCTURED_LOG_FINDINGS]
    return {
        "mode": "offline_structured_security_log_review",
        "asset": authorized_asset,
        "authorization_reference": scope.authorization_reference,
        "authorization_expires_at": scope.expires_at.astimezone(UTC).isoformat(),
        "scope_validated": True,
        "log_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "lines_reviewed": len(lines),
        "structured_records": structured_records,
        "unparsed_lines": unparsed_lines,
        "uncorrelated_auth_events": uncorrelated_auth_events,
        "findings": findings,
        "findings_truncated": findings_truncated,
        "actor_identifiers_included": False,
        "raw_log_values_included": False,
        "network_requests_made": False,
        "targets_modified": False,
    }
