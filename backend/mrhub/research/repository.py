"""Owner-scoped repository for problem opportunities and public-source evidence.

This layer stores curated observations. It does not crawl websites, infer personal
identities, or treat an unverified claim as validated market demand.
"""
from __future__ import annotations

import ipaddress
import math
import re
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

from mrhub.platform.catalog import get_domain

OPPORTUNITY_STATUSES = frozenset({
    "new", "validating", "validated", "prioritized", "in_progress", "deferred", "rejected"
})
STATUS_TRANSITIONS: dict[str, frozenset[str]] = {
    "new": frozenset({"validating", "rejected"}),
    "validating": frozenset({"new", "validated", "rejected"}),
    "validated": frozenset({"prioritized", "deferred", "rejected"}),
    "prioritized": frozenset({"in_progress", "deferred", "rejected"}),
    "in_progress": frozenset({"validated", "deferred"}),
    "deferred": frozenset({"validating", "rejected"}),
    "rejected": frozenset({"validating"}),
}
SOURCE_TYPES = frozenset({
    "public_discussion", "community_forum", "app_review", "research_report", "support_request", "other"
})
SIGNAL_STRENGTHS = frozenset({"low", "medium", "high"})
FEEDBACK_STATUSES = frozenset({"new", "reviewed", "converted", "dismissed"})
OUTCOME_METRICS = frozenset({
    "task_time_saved_minutes", "task_completion_rate_percent",
    "user_satisfaction_score", "error_rate_percent", "active_users", "operating_cost",
})
FEEDBACK_CONSENT_VERSION = "research-feedback-v1"


class ResearchError(RuntimeError):
    """Base error for research repository operations."""


class ResearchValidationError(ResearchError, ValueError):
    """An opportunity or evidence record violates its contract."""


class ResearchConflictError(ResearchValidationError):
    """A valid request conflicts with the current opportunity or evidence state."""


class ResearchNotFound(ResearchError, LookupError):
    """The requested owner-scoped opportunity does not exist."""


@dataclass(frozen=True)
class ResearchOpportunity:
    opportunity_id: str
    domain_id: str
    title: str
    problem_statement: str
    audience: str
    solution_hypothesis: str
    status: str
    impact_score: int | None
    frequency_score: int | None
    feasibility_score: int | None
    priority_score: int | None
    evidence_count: int
    created_at: str
    updated_at: str

    def as_dict(self) -> dict[str, object]:
        return {
            "opportunity_id": self.opportunity_id,
            "domain_id": self.domain_id,
            "title": self.title,
            "problem_statement": self.problem_statement,
            "audience": self.audience,
            "solution_hypothesis": self.solution_hypothesis,
            "status": self.status,
            "impact_score": self.impact_score,
            "frequency_score": self.frequency_score,
            "feasibility_score": self.feasibility_score,
            "priority_score": self.priority_score,
            "evidence_count": self.evidence_count,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True)
class ResearchEvidence:
    evidence_id: str
    opportunity_id: str
    source_type: str
    canonical_url: str
    source_label: str
    observation_summary: str
    signal_strength: str
    captured_at: str
    published_at: str | None

    def as_dict(self) -> dict[str, object]:
        return {
            "evidence_id": self.evidence_id,
            "opportunity_id": self.opportunity_id,
            "source_type": self.source_type,
            "canonical_url": self.canonical_url,
            "source_label": self.source_label,
            "observation_summary": self.observation_summary,
            "signal_strength": self.signal_strength,
            "captured_at": self.captured_at,
            "published_at": self.published_at,
        }


def _text(value: str, field: str, limit: int, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise ResearchValidationError(f"{field} must be text")
    normalized = value.strip()
    if (not normalized and not allow_empty) or len(normalized) > limit:
        raise ResearchValidationError(f"{field} must contain 1 to {limit} characters")
    return normalized


def _reject_feedback_identifiers(value: str, field: str) -> str:
    """Avoid collecting obvious direct identifiers in free-text feedback."""
    email_pattern = r"(?i)\b[\w.+-]+@[\w.-]+\.[A-Z]{2,}\b"
    phone_pattern = r"(?<!\w)(?:\+?\d[\d\s().-]{7,}\d)(?!\w)"
    secret_pattern = r"(?i)\b(?:password|passwd|api[_ -]?key|access[_ -]?token|secret)\s*[:=]\s*\S+"
    if re.search(email_pattern, value) or re.search(phone_pattern, value) or re.search(secret_pattern, value):
        raise ResearchValidationError(f"{field} must not contain contact details or credentials")
    return value


def canonicalize_evidence_url(value: str) -> str:
    """Accept a public HTTPS source URL without credentials, query, or fragment."""
    if not isinstance(value, str) or len(value) > 2048:
        raise ResearchValidationError("Source URL must contain at most 2048 characters")
    try:
        parsed = urlsplit(value.strip())
        host = parsed.hostname
        port = parsed.port
    except ValueError as exc:
        raise ResearchValidationError("Source URL is malformed") from exc
    if parsed.scheme.lower() != "https" or not host:
        raise ResearchValidationError("Evidence URL must use HTTPS and include a hostname")
    if parsed.username is not None or parsed.password is not None:
        raise ResearchValidationError("Evidence URL must not contain embedded credentials")
    if parsed.query or parsed.fragment or port not in (None, 443):
        raise ResearchValidationError("Evidence URL must not contain a query, fragment, or non-standard port")
    normalized_host = host.lower().rstrip(".")
    if not normalized_host:
        raise ResearchValidationError("Evidence URL must include a valid public hostname")
    if normalized_host in {"localhost", "localhost.localdomain"} or normalized_host.endswith(".local"):
        raise ResearchValidationError("Evidence URL must point to a public hostname")
    try:
        address = ipaddress.ip_address(normalized_host)
    except ValueError:
        address = None
    if address is not None:
        if not address.is_global:
            raise ResearchValidationError("Evidence URL must not point to a private or non-global IP address")
        normalized_host = address.compressed
        netloc = f"[{normalized_host}]" if address.version == 6 else normalized_host
    else:
        try:
            ascii_host = normalized_host.encode("idna").decode("ascii").lower()
        except UnicodeError as exc:
            raise ResearchValidationError("Evidence URL hostname is malformed") from exc
        labels = ascii_host.split(".")
        if (
            len(ascii_host) > 253
            or len(labels) < 2
            or any(
                not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
                for label in labels
            )
        ):
            raise ResearchValidationError("Evidence URL hostname is malformed")
        netloc = ascii_host
    return urlunsplit(("https", netloc, parsed.path.rstrip("/"), "", ""))


class ResearchRepository:
    """Persist curated opportunity records with strict owner and evidence boundaries."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
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
    def _from_row(row: sqlite3.Row) -> ResearchOpportunity:
        scores = (row["impact_score"], row["frequency_score"], row["feasibility_score"])
        priority = None
        if all(score is not None for score in scores):
            priority = round((scores[0] * 0.40 + scores[1] * 0.35 + scores[2] * 0.25) * 20)
        return ResearchOpportunity(
            opportunity_id=row["opportunity_id"], domain_id=row["domain_id"], title=row["title"],
            problem_statement=row["problem_statement"], audience=row["audience"],
            solution_hypothesis=row["solution_hypothesis"], status=row["status"],
            impact_score=row["impact_score"], frequency_score=row["frequency_score"],
            feasibility_score=row["feasibility_score"], priority_score=priority,
            evidence_count=row["evidence_count"], created_at=row["created_at"], updated_at=row["updated_at"],
        )

    def create_opportunity(
        self, *, owner_user_id: str, domain_id: str, title: str,
        problem_statement: str, audience: str, solution_hypothesis: str = "",
    ) -> ResearchOpportunity:
        owner = _text(owner_user_id, "Owner ID", 200)
        if get_domain(domain_id) is None:
            raise ResearchValidationError("Unknown capability domain")
        title = _text(title, "Title", 160)
        problem_statement = _text(problem_statement, "Problem statement", 4000)
        audience = _text(audience, "Audience", 240)
        solution_hypothesis = _text(solution_hypothesis, "Solution hypothesis", 2000, allow_empty=True)
        now = self._now()
        opportunity_id = str(uuid4())
        with self._connection() as connection:
            connection.execute(
                """INSERT INTO research_opportunities (
                    opportunity_id, owner_user_id, domain_id, title, problem_statement,
                    audience, solution_hypothesis, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'new', ?, ?)""",
                (opportunity_id, owner, domain_id, title, problem_statement, audience, solution_hypothesis, now, now),
            )
        return self.get_opportunity(owner_user_id=owner, opportunity_id=opportunity_id)

    def list_opportunities(
        self, *, owner_user_id: str, status: str | None = None,
        domain_id: str | None = None, limit: int = 50,
    ) -> list[ResearchOpportunity]:
        owner = _text(owner_user_id, "Owner ID", 200)
        if status is not None and status not in OPPORTUNITY_STATUSES:
            raise ResearchValidationError("Unsupported opportunity status")
        if domain_id is not None and get_domain(domain_id) is None:
            raise ResearchValidationError("Unknown capability domain")
        bounded_limit = max(1, min(int(limit), 100))
        with self._connection() as connection:
            rows = connection.execute(
                """SELECT o.*,
                    (SELECT COUNT(*) FROM research_evidence e
                     WHERE e.opportunity_id = o.opportunity_id
                       AND e.owner_user_id = o.owner_user_id) AS evidence_count
                   FROM research_opportunities o
                   WHERE o.owner_user_id = ?
                     AND (? IS NULL OR o.status = ?)
                     AND (? IS NULL OR o.domain_id = ?)
                   ORDER BY o.updated_at DESC
                   LIMIT ?""",
                (owner, status, status, domain_id, domain_id, bounded_limit),
            ).fetchall()
        return [self._from_row(row) for row in rows]

    def get_opportunity(self, *, owner_user_id: str, opportunity_id: str) -> ResearchOpportunity:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT o.*, (SELECT COUNT(*) FROM research_evidence e "
                "WHERE e.opportunity_id = o.opportunity_id AND e.owner_user_id = o.owner_user_id) AS evidence_count "
                "FROM research_opportunities o WHERE o.opportunity_id = ? AND o.owner_user_id = ?",
                (opportunity_id, owner_user_id),
            ).fetchone()
        if row is None:
            raise ResearchNotFound("Research opportunity not found")
        return self._from_row(row)

    def list_evidence(self, *, owner_user_id: str, opportunity_id: str) -> list[ResearchEvidence]:
        self.get_opportunity(owner_user_id=owner_user_id, opportunity_id=opportunity_id)
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT evidence_id, opportunity_id, source_type, canonical_url, source_label, "
                "observation_summary, signal_strength, captured_at, published_at "
                "FROM research_evidence WHERE owner_user_id = ? AND opportunity_id = ? "
                "ORDER BY captured_at DESC LIMIT 100", (owner_user_id, opportunity_id),
            ).fetchall()
        return [ResearchEvidence(**dict(row)) for row in rows]

    def add_evidence(
        self, *, owner_user_id: str, opportunity_id: str, source_type: str,
        source_url: str, source_label: str, observation_summary: str,
        signal_strength: str = "medium", published_at: str | None = None,
    ) -> ResearchEvidence:
        self.get_opportunity(owner_user_id=owner_user_id, opportunity_id=opportunity_id)
        if source_type not in SOURCE_TYPES:
            raise ResearchValidationError("Unsupported evidence source type")
        if signal_strength not in SIGNAL_STRENGTHS:
            raise ResearchValidationError("Unsupported signal strength")
        canonical_url = canonicalize_evidence_url(source_url)
        source_label = _text(source_label, "Source label", 120)
        observation_summary = _text(observation_summary, "Observation summary", 2000)
        if published_at is not None:
            published_at = _text(published_at, "Published timestamp", 40)
            try:
                datetime.fromisoformat(published_at)
            except ValueError as exc:
                raise ResearchValidationError("Published timestamp must be ISO 8601") from exc
        evidence_id = str(uuid4())
        captured_at = self._now()
        try:
            with self._connection() as connection:
                connection.execute(
                    """INSERT INTO research_evidence (
                        evidence_id, opportunity_id, owner_user_id, source_type, canonical_url,
                        source_label, observation_summary, signal_strength, captured_at, published_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (evidence_id, opportunity_id, owner_user_id, source_type, canonical_url,
                     source_label, observation_summary, signal_strength, captured_at, published_at),
                )
                connection.execute(
                    "UPDATE research_opportunities SET updated_at = ? WHERE opportunity_id = ? AND owner_user_id = ?",
                    (captured_at, opportunity_id, owner_user_id),
                )
        except sqlite3.IntegrityError as exc:
            raise ResearchConflictError("This source URL is already attached to the opportunity") from exc
        return ResearchEvidence(
            evidence_id=evidence_id, opportunity_id=opportunity_id, source_type=source_type,
            canonical_url=canonical_url, source_label=source_label,
            observation_summary=observation_summary, signal_strength=signal_strength,
            captured_at=captured_at, published_at=published_at,
        )

    def update_assessment(
        self, *, owner_user_id: str, opportunity_id: str, status: str | None = None,
        impact_score: int | None = None, frequency_score: int | None = None,
        feasibility_score: int | None = None, solution_hypothesis: str | None = None,
    ) -> ResearchOpportunity:
        current = self.get_opportunity(owner_user_id=owner_user_id, opportunity_id=opportunity_id)
        next_status = current.status if status is None else status
        if next_status not in OPPORTUNITY_STATUSES:
            raise ResearchValidationError("Unsupported opportunity status")
        if next_status != current.status and next_status not in STATUS_TRANSITIONS[current.status]:
            raise ResearchConflictError(f"Invalid opportunity transition: {current.status} -> {next_status}")
        scores = {"impact_score": impact_score, "frequency_score": frequency_score, "feasibility_score": feasibility_score}
        for name, value in scores.items():
            if value is not None and (isinstance(value, bool) or not 1 <= value <= 5):
                raise ResearchValidationError(f"{name} must be an integer from 1 to 5")
        effective_scores = (
            current.impact_score if impact_score is None else impact_score,
            current.frequency_score if frequency_score is None else frequency_score,
            current.feasibility_score if feasibility_score is None else feasibility_score,
        )
        if next_status == "validated":
            with self._connection() as connection:
                evidence = connection.execute(
                    "SELECT canonical_url, source_type FROM research_evidence "
                    "WHERE owner_user_id = ? AND opportunity_id = ?",
                    (owner_user_id, opportunity_id),
                ).fetchall()
            source_count = len({row["canonical_url"] for row in evidence})
            type_count = len({row["source_type"] for row in evidence})
            host_count = len({
                urlsplit(row["canonical_url"]).hostname
                for row in evidence
                if urlsplit(row["canonical_url"]).hostname
            })
            if source_count < 2 or type_count < 2 or host_count < 2:
                raise ResearchConflictError(
                    "Validation requires two distinct public URLs, two source types, and two distinct hostnames"
                )
        if next_status == "prioritized" and any(score is None for score in effective_scores):
            raise ResearchConflictError(
                "Prioritization requires impact, frequency, and feasibility scores"
            )
        hypothesis = current.solution_hypothesis if solution_hypothesis is None else _text(
            solution_hypothesis, "Solution hypothesis", 2000, allow_empty=True
        )
        now = self._now()
        with self._connection() as connection:
            cursor = connection.execute(
                """UPDATE research_opportunities SET status = ?,
                    impact_score = COALESCE(?, impact_score),
                    frequency_score = COALESCE(?, frequency_score),
                    feasibility_score = COALESCE(?, feasibility_score),
                    solution_hypothesis = ?, updated_at = ?
                   WHERE opportunity_id = ? AND owner_user_id = ? AND status = ?""",
                (next_status, impact_score, frequency_score, feasibility_score, hypothesis,
                 now, opportunity_id, owner_user_id, current.status),
            )
            if cursor.rowcount != 1:
                raise ResearchConflictError("Opportunity changed concurrently; reload before retrying")
        return self.get_opportunity(owner_user_id=owner_user_id, opportunity_id=opportunity_id)


    def create_feedback(
        self, *, owner_user_id: str, domain_id: str, audience_segment: str,
        need_summary: str, current_workaround: str = "", impact_score: int | None = None,
        frequency_score: int | None = None, consent_to_research: bool = False,
    ) -> dict[str, object]:
        owner = _text(owner_user_id, "Owner ID", 200)
        if get_domain(domain_id) is None:
            raise ResearchValidationError("Unknown capability domain")
        if consent_to_research is not True:
            raise ResearchValidationError("Explicit consent to use this feedback for product research is required")
        for name, value in (("impact_score", impact_score), ("frequency_score", frequency_score)):
            if value is not None and (isinstance(value, bool) or not 1 <= value <= 5):
                raise ResearchValidationError(f"{name} must be an integer from 1 to 5")
        audience_segment = _reject_feedback_identifiers(_text(audience_segment, "Audience segment", 120), "Audience segment")
        need_summary = _reject_feedback_identifiers(_text(need_summary, "Need summary", 2000), "Need summary")
        current_workaround = _reject_feedback_identifiers(
            _text(current_workaround, "Current workaround", 1200, allow_empty=True),
            "Current workaround",
        )
        feedback_id = str(uuid4())
        now = self._now()
        with self._connection() as connection:
            connection.execute(
                """INSERT INTO research_feedback (
                    feedback_id, owner_user_id, domain_id, audience_segment, need_summary,
                    current_workaround, impact_score, frequency_score, consent_to_research,
                    consent_version, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, 'new', ?, ?)""",
                (feedback_id, owner, domain_id, audience_segment, need_summary, current_workaround,
                 impact_score, frequency_score, FEEDBACK_CONSENT_VERSION, now, now),
            )
        return self.get_feedback(owner_user_id=owner, feedback_id=feedback_id)

    def get_feedback(self, *, owner_user_id: str, feedback_id: str) -> dict[str, object]:
        with self._connection() as connection:
            row = connection.execute(
                """SELECT feedback_id, domain_id, audience_segment, need_summary,
                          current_workaround, impact_score, frequency_score, consent_version,
                          status, created_at, updated_at
                   FROM research_feedback WHERE feedback_id = ? AND owner_user_id = ?""",
                (feedback_id, owner_user_id),
            ).fetchone()
        if row is None:
            raise ResearchNotFound("Research feedback not found")
        return dict(row)

    def list_feedback(
        self, *, owner_user_id: str, status: str | None = None,
        domain_id: str | None = None, limit: int = 50,
    ) -> list[dict[str, object]]:
        owner = _text(owner_user_id, "Owner ID", 200)
        if status is not None and status not in FEEDBACK_STATUSES:
            raise ResearchValidationError("Unsupported feedback status")
        if domain_id is not None and get_domain(domain_id) is None:
            raise ResearchValidationError("Unknown capability domain")
        bounded_limit = max(1, min(int(limit), 100))
        with self._connection() as connection:
            rows = connection.execute(
                """SELECT feedback_id, domain_id, audience_segment, need_summary,
                          current_workaround, impact_score, frequency_score, consent_version,
                          status, created_at, updated_at
                   FROM research_feedback
                   WHERE owner_user_id = ?
                     AND (? IS NULL OR status = ?)
                     AND (? IS NULL OR domain_id = ?)
                   ORDER BY created_at DESC LIMIT ?""",
                (owner, status, status, domain_id, domain_id, bounded_limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def update_feedback_status(
        self, *, owner_user_id: str, feedback_id: str, status: str,
    ) -> dict[str, object]:
        if status not in FEEDBACK_STATUSES:
            raise ResearchValidationError("Unsupported feedback status")
        now = self._now()
        with self._connection() as connection:
            cursor = connection.execute(
                """UPDATE research_feedback SET status = ?, updated_at = ?
                   WHERE feedback_id = ? AND owner_user_id = ?""",
                (status, now, feedback_id, owner_user_id),
            )
        if cursor.rowcount != 1:
            raise ResearchNotFound("Research feedback not found")
        return self.get_feedback(owner_user_id=owner_user_id, feedback_id=feedback_id)

    def delete_feedback(self, *, owner_user_id: str, feedback_id: str) -> bool:
        with self._connection() as connection:
            cursor = connection.execute(
                "DELETE FROM research_feedback WHERE feedback_id = ? AND owner_user_id = ?",
                (feedback_id, owner_user_id),
            )
        return cursor.rowcount == 1

    def create_outcome_measurement(
        self, *, owner_user_id: str, opportunity_id: str, metric_name: str,
        baseline_value: float, observed_value: float, unit: str, sample_size: int,
        period_start: str, period_end: str, notes: str = "",
    ) -> dict[str, object]:
        owner = _text(owner_user_id, "Owner ID", 200)
        self.get_opportunity(owner_user_id=owner, opportunity_id=opportunity_id)
        if metric_name not in OUTCOME_METRICS:
            raise ResearchValidationError("Unsupported outcome metric")
        for name, value in (("baseline_value", baseline_value), ("observed_value", observed_value)):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                raise ResearchValidationError(f"{name} must be a finite non-negative number")
        if isinstance(sample_size, bool) or not isinstance(sample_size, int) or not 1 <= sample_size <= 1_000_000:
            raise ResearchValidationError("sample_size must be an integer from 1 to 1000000")
        unit = _text(unit, "Unit", 40)
        notes = _text(notes, "Notes", 1200, allow_empty=True)
        try:
            start = datetime.fromisoformat(_text(period_start, "Period start", 40))
            end = datetime.fromisoformat(_text(period_end, "Period end", 40))
        except ValueError as exc:
            raise ResearchValidationError("Measurement period must use ISO 8601 timestamps") from exc
        if (
            start.tzinfo is None or start.utcoffset() is None
            or end.tzinfo is None or end.utcoffset() is None
        ):
            raise ResearchValidationError("Measurement period timestamps must include a timezone")
        if start.tzinfo is None or end.tzinfo is None:
            raise ResearchValidationError("Measurement timestamps must include an explicit timezone offset")
        if end < start:
            raise ResearchValidationError("Measurement period end must not precede its start")
        measurement_id = str(uuid4())
        recorded_at = self._now()
        with self._connection() as connection:
            connection.execute(
                """INSERT INTO research_outcome_measurements (
                    measurement_id, opportunity_id, owner_user_id, metric_name,
                    baseline_value, observed_value, unit, sample_size,
                    period_start, period_end, notes, recorded_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (measurement_id, opportunity_id, owner, metric_name, float(baseline_value),
                 float(observed_value), unit, sample_size, start.isoformat(), end.isoformat(),
                 notes, recorded_at),
            )
        return self.get_outcome_measurement(owner_user_id=owner, measurement_id=measurement_id)

    def get_outcome_measurement(
        self, *, owner_user_id: str, measurement_id: str,
    ) -> dict[str, object]:
        with self._connection() as connection:
            row = connection.execute(
                """SELECT measurement_id, opportunity_id, metric_name, baseline_value,
                          observed_value, unit, sample_size, period_start, period_end, notes, recorded_at
                   FROM research_outcome_measurements
                   WHERE measurement_id = ? AND owner_user_id = ?""",
                (measurement_id, owner_user_id),
            ).fetchone()
        if row is None:
            raise ResearchNotFound("Outcome measurement not found")
        return dict(row)

    def list_outcome_measurements(
        self, *, owner_user_id: str, opportunity_id: str,
    ) -> list[dict[str, object]]:
        self.get_opportunity(owner_user_id=owner_user_id, opportunity_id=opportunity_id)
        with self._connection() as connection:
            rows = connection.execute(
                """SELECT measurement_id, opportunity_id, metric_name, baseline_value,
                          observed_value, unit, sample_size, period_start, period_end, notes, recorded_at
                   FROM research_outcome_measurements
                   WHERE owner_user_id = ? AND opportunity_id = ?
                   ORDER BY recorded_at DESC LIMIT 100""",
                (owner_user_id, opportunity_id),
            ).fetchall()
        return [dict(row) for row in rows]
