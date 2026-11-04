"""Persistent catalog for third-party capabilities awaiting controlled integration.

This module records source metadata and review evidence only. It never downloads,
imports, installs, or executes code from a discovered source.
"""

from __future__ import annotations

import ipaddress
import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

SourceKind = Literal["github_repository", "documentation", "package", "api", "other"]
IntegrationType = Literal["connector", "skill", "python_package", "http_api", "adapter", "manual"]
CandidateStatus = Literal["discovered", "reviewing", "approved", "rejected", "disabled"]

SOURCE_KINDS = frozenset({"github_repository", "documentation", "package", "api", "other"})
INTEGRATION_TYPES = frozenset(
    {"connector", "skill", "python_package", "http_api", "adapter", "manual"}
)
STATUSES = frozenset({"discovered", "reviewing", "approved", "rejected", "disabled"})
STATUS_TRANSITIONS: dict[str, frozenset[str]] = {
    "discovered": frozenset({"reviewing", "rejected"}),
    "reviewing": frozenset({"discovered", "approved", "rejected"}),
    "approved": frozenset({"reviewing", "disabled"}),
    "rejected": frozenset({"reviewing"}),
    "disabled": frozenset({"reviewing", "rejected"}),
}


class CapabilityCatalogError(RuntimeError):
    """Base error for catalog operations."""


class CapabilityValidationError(CapabilityCatalogError, ValueError):
    """A candidate manifest or review transition violates catalog policy."""


class CapabilityNotFound(CapabilityCatalogError, LookupError):
    """A candidate does not exist in the local catalog."""


@dataclass(frozen=True)
class CapabilityCandidate:
    candidate_id: str
    canonical_url: str
    display_name: str
    summary: str
    source_kind: SourceKind
    license_id: str
    integration_type: IntegrationType
    status: CandidateStatus
    capabilities: tuple[str, ...]
    evidence: dict[str, str]
    created_at: str
    updated_at: str

    def as_dict(self) -> dict[str, object]:
        return {
            "candidate_id": self.candidate_id,
            "canonical_url": self.canonical_url,
            "display_name": self.display_name,
            "summary": self.summary,
            "source_kind": self.source_kind,
            "license_id": self.license_id,
            "integration_type": self.integration_type,
            "status": self.status,
            "capabilities": list(self.capabilities),
            "evidence": dict(self.evidence),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


def canonicalize_source_url(value: str) -> str:
    """Accept a public HTTPS source URL and remove only harmless URL variation."""
    if not isinstance(value, str) or len(value) > 2048:
        raise CapabilityValidationError("Source URL must be a string of at most 2048 characters")
    try:
        parsed = urlsplit(value.strip())
        host = parsed.hostname
        port = parsed.port
    except ValueError as exc:
        raise CapabilityValidationError("Source URL is malformed") from exc
    if parsed.scheme.lower() != "https" or not host:
        raise CapabilityValidationError("Source URL must use HTTPS and include a hostname")
    if parsed.username is not None or parsed.password is not None:
        raise CapabilityValidationError("Source URL must not contain embedded credentials")
    if parsed.query or parsed.fragment:
        raise CapabilityValidationError("Source URL must not contain a query or fragment")
    normalized_host = host.lower().rstrip(".")
    if normalized_host in {"localhost", "localhost.localdomain"} or normalized_host.endswith(
        ".local"
    ):
        raise CapabilityValidationError("Source URL must point to a public hostname")
    try:
        address = ipaddress.ip_address(normalized_host)
    except ValueError:
        address = None
    if address is not None and not address.is_global:
        raise CapabilityValidationError("Private or non-global IP source URLs are not allowed")
    if port not in (None, 443):
        raise CapabilityValidationError("Source URL must use the standard HTTPS port")
    path = parsed.path.rstrip("/")
    path = path.removesuffix(".git")
    return urlunsplit(("https", normalized_host, path, "", ""))


class CapabilityRegistry:
    """Store, review, and query source candidates without executing upstream code."""

    MAX_CAPABILITIES = 50
    MAX_CAPABILITY_LENGTH = 80
    REQUIRED_APPROVAL_EVIDENCE = frozenset(
        {"license_url", "security_review", "compatibility_notes", "test_plan"}
    )

    def __init__(self, database_path: Path) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        # Reuse the project's single versioned schema authority.
        from mrhub.infrastructure.database import TaskRepository

        TaskRepository(self.database_path).initialize()

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()

    @staticmethod
    def _normalize_text(value: str, field: str, limit: int, *, allow_empty: bool = False) -> str:
        if not isinstance(value, str):
            raise CapabilityValidationError(f"{field} must be text")
        normalized = value.strip()
        if not normalized and not allow_empty:
            raise CapabilityValidationError(f"{field} must not be empty")
        if len(normalized) > limit:
            raise CapabilityValidationError(f"{field} must contain at most {limit} characters")
        return normalized

    @classmethod
    def _normalize_capabilities(cls, values: list[str] | tuple[str, ...]) -> tuple[str, ...]:
        if not isinstance(values, (list, tuple)) or len(values) > cls.MAX_CAPABILITIES:
            raise CapabilityValidationError("Capabilities must be a list of at most 50 items")
        result: list[str] = []
        seen: set[str] = set()
        for item in values:
            capability = cls._normalize_text(item, "Capability", cls.MAX_CAPABILITY_LENGTH)
            if capability not in seen:
                result.append(capability)
                seen.add(capability)
        return tuple(result)

    @staticmethod
    def _row_to_candidate(row: sqlite3.Row) -> CapabilityCandidate:
        return CapabilityCandidate(
            candidate_id=row["candidate_id"],
            canonical_url=row["canonical_url"],
            display_name=row["display_name"],
            summary=row["summary"],
            source_kind=row["source_kind"],
            license_id=row["license_id"],
            integration_type=row["integration_type"],
            status=row["status"],
            capabilities=tuple(json.loads(row["capabilities_json"])),
            evidence=json.loads(row["evidence_json"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def add_candidate(
        self,
        *,
        source_url: str,
        display_name: str,
        summary: str = "",
        source_kind: SourceKind = "github_repository",
        integration_type: IntegrationType = "manual",
        capabilities: list[str] | tuple[str, ...] = (),
        license_id: str = "unknown",
    ) -> CapabilityCandidate:
        """Register a candidate; this does not fetch or execute the remote source."""
        canonical_url = canonicalize_source_url(source_url)
        display_name = self._normalize_text(display_name, "Display name", 160)
        summary = self._normalize_text(summary, "Summary", 1000, allow_empty=True)
        license_id = self._normalize_text(license_id, "License identifier", 80)
        if source_kind not in SOURCE_KINDS:
            raise CapabilityValidationError("Unsupported source kind")
        if integration_type not in INTEGRATION_TYPES:
            raise CapabilityValidationError("Unsupported integration type")
        normalized_capabilities = self._normalize_capabilities(capabilities)
        now = self._now()
        candidate_id = str(uuid4())
        try:
            with self._connection() as connection:
                connection.execute(
                    """INSERT INTO capability_candidates (
                        candidate_id, canonical_url, display_name, summary, source_kind,
                        license_id, integration_type, status, capabilities_json, evidence_json,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, 'discovered', ?, '{}', ?, ?)""",
                    (
                        candidate_id,
                        canonical_url,
                        display_name,
                        summary,
                        source_kind,
                        license_id,
                        integration_type,
                        json.dumps(normalized_capabilities, ensure_ascii=False),
                        now,
                        now,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise CapabilityValidationError(
                "This canonical source is already in the catalog"
            ) from exc
        return self.get(candidate_id)

    def get(self, candidate_id: str) -> CapabilityCandidate:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM capability_candidates WHERE candidate_id = ?", (candidate_id,)
            ).fetchone()
        if row is None:
            raise CapabilityNotFound("Capability candidate not found")
        return self._row_to_candidate(row)

    def list_candidates(
        self, *, status: CandidateStatus | None = None, limit: int = 50
    ) -> list[CapabilityCandidate]:
        bounded_limit = max(1, min(int(limit), 100))
        if status is not None and status not in STATUSES:
            raise CapabilityValidationError("Unsupported candidate status")
        with self._connection() as connection:
            if status is None:
                rows = connection.execute(
                    "SELECT * FROM capability_candidates ORDER BY updated_at DESC LIMIT ?",
                    (bounded_limit,),
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT * FROM capability_candidates WHERE status = ? "
                    "ORDER BY updated_at DESC LIMIT ?",
                    (status, bounded_limit),
                ).fetchall()
        return [self._row_to_candidate(row) for row in rows]

    def transition(
        self,
        candidate_id: str,
        status: CandidateStatus,
        *,
        license_id: str | None = None,
        evidence: dict[str, str] | None = None,
    ) -> CapabilityCandidate:
        """Change review state; approval requires explicit license/security/test evidence."""
        if status not in STATUSES:
            raise CapabilityValidationError("Unsupported candidate status")
        current = self.get(candidate_id)
        if status not in STATUS_TRANSITIONS[current.status]:
            raise CapabilityValidationError(
                f"Invalid capability status transition: {current.status} -> {status}"
            )
        next_license = (
            current.license_id
            if license_id is None
            else self._normalize_text(license_id, "License identifier", 80)
        )
        next_evidence = dict(current.evidence)
        if evidence is not None:
            if not isinstance(evidence, dict):
                raise CapabilityValidationError("Review evidence must be an object")
            for key, value in evidence.items():
                if key not in self.REQUIRED_APPROVAL_EVIDENCE:
                    raise CapabilityValidationError(f"Unsupported review evidence field: {key}")
                next_evidence[key] = self._normalize_text(value, key, 2000)
        if status == "approved":
            missing = self.REQUIRED_APPROVAL_EVIDENCE - next_evidence.keys()
            if next_license.lower() in {"", "unknown", "none", "unlicensed"} or missing:
                raise CapabilityValidationError(
                    "Approval requires a known license and license URL, security review, "
                    "compatibility notes, and a test plan"
                )
            try:
                canonicalize_source_url(next_evidence["license_url"])
            except CapabilityValidationError as exc:
                raise CapabilityValidationError(
                    "Approval requires a public HTTPS license URL without credentials or query parameters"
                ) from exc
        now = self._now()
        with self._connection() as connection:
            cursor = connection.execute(
                """UPDATE capability_candidates
                   SET status = ?, license_id = ?, evidence_json = ?, updated_at = ?
                   WHERE candidate_id = ? AND status = ?""",
                (
                    status,
                    next_license,
                    json.dumps(next_evidence, ensure_ascii=False, sort_keys=True),
                    now,
                    candidate_id,
                    current.status,
                ),
            )
            if cursor.rowcount != 1:
                raise CapabilityCatalogError(
                    "Candidate changed concurrently; reload before retrying"
                )
        return self.get(candidate_id)
