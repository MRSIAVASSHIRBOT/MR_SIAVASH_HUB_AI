"""Owner-scoped memory persistence and FTS5 retrieval."""
from __future__ import annotations

import json
import math
import re
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from mrhub.infrastructure.database import TaskRepository


class MemoryRepository:
    """Store explicit memory records and search only the authenticated owner's data."""

    MEMORY_TYPES = frozenset({"unspecified", "episodic", "semantic", "procedural"})

    _SECRET_PATTERNS = (
        re.compile(r"(?i)\b(?:password|passwd|api[_ -]?key|access[_ -]?token|refresh[_ -]?token|secret)\s*[:=]\s*\S+"),
        re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
        re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
        re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{16,}\b"),
        re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
        re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{20,}"),
    )

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self.tasks = TaskRepository(database_path)
        self.tasks.initialize()

    @staticmethod
    def validate_memory_text(value: object | None) -> str | None:
        """Reject obvious credential patterns as defense-in-depth.

        This heuristic cannot guarantee that every credential format is detected.
        """
        if value is None:
            return None
        if not isinstance(value, str):
            raise TypeError("Memory fields must be text")
        if any(pattern.search(value) for pattern in MemoryRepository._SECRET_PATTERNS):
            raise ValueError("Memory must not contain credentials or authentication secrets")
        return value

    @staticmethod
    def _validate_confidence(value: object) -> float:
        """Validate owner-supplied confidence at the persistence boundary."""
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError("Confidence must be a numeric value")
        try:
            numeric = float(value)
        except (OverflowError, TypeError, ValueError) as exc:
            raise ValueError("Confidence must be a finite number between 0 and 1") from exc
        if not math.isfinite(numeric) or not 0.0 <= numeric <= 1.0:
            raise ValueError("Confidence must be a finite number between 0 and 1")
        return numeric

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()

    @staticmethod
    def _serialize_expiry(value: datetime | None) -> str | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Expiry timestamps must include a timezone")
        return value.astimezone(UTC).isoformat()

    @staticmethod
    def _record(row) -> dict[str, object]:
        return {
            "memory_id": row["memory_id"],
            "owner_user_id": row["owner_user_id"],
            "scope": row["scope"],
            "memory_type": row["memory_type"],
            "category": row["category"],
            "content": row["content"],
            "provenance": row["provenance"],
            "confidence": row["confidence"],
            "verification_status": row["verification_status"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "expires_at": row["expires_at"],
        }

    def create(self, owner_user_id: str, values: dict[str, object]) -> dict[str, object]:
        self.validate_memory_text(values.get("content"))
        self.validate_memory_text(values.get("provenance"))
        memory_type = values.get("memory_type", "unspecified")
        if not isinstance(memory_type, str) or memory_type not in self.MEMORY_TYPES:
            raise ValueError("Unsupported memory type")
        confidence = self._validate_confidence(values.get("confidence", 0.7))
        memory_id = str(uuid4())
        now = self._now()
        expires_at = self._serialize_expiry(values.get("expires_at"))  # type: ignore[arg-type]
        with self.tasks._connection() as connection:
            connection.execute(
                """
                INSERT INTO memory_entries (
                    memory_id, owner_user_id, scope, memory_type, category, content, provenance,
                    confidence, verification_status, created_at, updated_at, expires_at
                ) VALUES (?, ?, 'private', ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    memory_id,
                    owner_user_id,
                    memory_type,
                    values["category"],
                    values["content"],
                    values.get("provenance", "user-authored"),
                    confidence,
                    values.get("verification_status", "user_authored"),
                    now,
                    now,
                    expires_at,
                ),
            )
            row = connection.execute(
                "SELECT * FROM memory_entries WHERE memory_id = ? AND owner_user_id = ?",
                (memory_id, owner_user_id),
            ).fetchone()
        assert row is not None
        return self._record(row)

    def get(self, owner_user_id: str, memory_id: UUID, *, include_expired: bool = False):
        query = "SELECT * FROM memory_entries WHERE memory_id = ? AND owner_user_id = ?"
        params: tuple[object, ...] = (str(memory_id), owner_user_id)
        if not include_expired:
            query += " AND (expires_at IS NULL OR expires_at > ?)"
            params += (self._now(),)
        with self.tasks._connection() as connection:
            row = connection.execute(query, params).fetchone()
        return self._record(row) if row is not None else None

    def list_entries(
        self, owner_user_id: str, limit: int = 50, *, include_expired: bool = False
    ) -> list[dict[str, object]]:
        bounded_limit = max(1, min(limit, 100))
        query = "SELECT * FROM memory_entries WHERE owner_user_id = ?"
        params: tuple[object, ...] = (owner_user_id,)
        if not include_expired:
            query += " AND (expires_at IS NULL OR expires_at > ?)"
            params += (self._now(),)
        query += " ORDER BY updated_at DESC LIMIT ?"
        params += (bounded_limit,)
        with self.tasks._connection() as connection:
            rows = connection.execute(query, params).fetchall()
        return [self._record(row) for row in rows]

    def update(
        self, owner_user_id: str, memory_id: UUID, changes: dict[str, object]
    ) -> dict[str, object] | None:
        self.validate_memory_text(changes.get("content"))
        self.validate_memory_text(changes.get("provenance"))
        allowed = {
            "memory_type",
            "category",
            "content",
            "provenance",
            "confidence",
            "verification_status",
            "expires_at",
        }
        assignments: list[str] = []
        values: list[object] = []
        for key, value in changes.items():
            if key not in allowed:
                raise ValueError("Unsupported memory field")
            if key == "memory_type" and (
                not isinstance(value, str) or value not in self.MEMORY_TYPES
            ):
                raise ValueError("Unsupported memory type")
            if key == "confidence":
                value = self._validate_confidence(value)
            if key == "expires_at":
                value = self._serialize_expiry(value)  # type: ignore[arg-type]
            assignments.append(f"{key} = ?")
            values.append(value)
        if not assignments:
            raise ValueError("At least one field must be updated")
        assignments.append("updated_at = ?")
        values.append(self._now())
        values.extend((str(memory_id), owner_user_id))
        with self.tasks._connection() as connection:
            cursor = connection.execute(
                f"UPDATE memory_entries SET {', '.join(assignments)} "  # nosec B608 -- identifiers come only from the fixed allowlist; values are bound.
                "WHERE memory_id = ? AND owner_user_id = ?",
                tuple(values),
            )
            if cursor.rowcount != 1:
                return None
            row = connection.execute(
                "SELECT * FROM memory_entries WHERE memory_id = ? AND owner_user_id = ?",
                (str(memory_id), owner_user_id),
            ).fetchone()
        return self._record(row) if row is not None else None

    def delete(self, owner_user_id: str, memory_id: UUID) -> bool:
        with self.tasks._connection() as connection:
            cursor = connection.execute(
                "DELETE FROM memory_entries WHERE memory_id = ? AND owner_user_id = ?",
                (str(memory_id), owner_user_id),
            )
        return cursor.rowcount == 1

    def delete_expired(self, owner_user_id: str) -> int:
        with self.tasks._connection() as connection:
            cursor = connection.execute(
                "DELETE FROM memory_entries WHERE owner_user_id = ? "
                "AND expires_at IS NOT NULL AND expires_at <= ?",
                (owner_user_id, self._now()),
            )
        return cursor.rowcount

    @staticmethod
    def _freshness_score(updated_at: object, now: datetime) -> float:
        """Return a bounded 90-day exponential freshness signal."""
        if not isinstance(updated_at, str) or not updated_at:
            return 0.0
        try:
            parsed = datetime.fromisoformat(updated_at)
        except ValueError:
            return 0.0
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            return 0.0
        age_seconds = max(0.0, (now - parsed.astimezone(UTC)).total_seconds())
        return math.exp(-age_seconds / (90 * 24 * 60 * 60))

    def search(
        self,
        owner_user_id: str,
        query: str,
        limit: int = 10,
        *,
        memory_types: list[str] | tuple[str, ...] | set[str] | frozenset[str] | None = None,
    ) -> list[dict[str, object]]:
        """Rerank owner-scoped lexical candidates with typed filtering and trust signals.

        Owner and expiry restrictions, plus optional memory-type filters, are
        applied in SQL before any ranking. Scores order retrieval relevance only;
        they never establish truth, independently verify content, or grant authority.
        """
        if type(limit) is not int or limit < 1:
            raise ValueError("Memory search limit must be a positive integer")
        terms = re.findall(r"[^\W_]+", query, flags=re.UNICODE)
        if not terms:
            return []
        # Token extraction removes FTS operators and syntax supplied by callers.
        match_expression = " AND ".join(
            f'"{term.replace(chr(34), chr(34) * 2)}"' for term in terms[:12]
        )
        bounded_limit = max(1, min(limit, 25))
        candidate_limit = 100
        selected_types: tuple[str, ...] | None = None
        if memory_types is not None:
            if any(not isinstance(memory_type, str) for memory_type in memory_types):
                raise ValueError("Unsupported memory type")
            selected_types = tuple(sorted(set(memory_types)))
            if not selected_types:
                return []
            if any(memory_type not in self.MEMORY_TYPES for memory_type in selected_types):
                raise ValueError("Unsupported memory type")

        type_filter_json = (
            json.dumps(selected_types, separators=(",", ":"))
            if selected_types is not None
            else None
        )
        now = datetime.now(UTC)
        query_params: tuple[object, ...] = (
            match_expression,
            owner_user_id,
            now.isoformat(),
            type_filter_json,
            type_filter_json,
            candidate_limit,
        )

        with self.tasks._connection() as connection:
            rows = connection.execute(
                """
                SELECT m.*, bm25(memory_entries_fts) AS lexical_rank
                FROM memory_entries_fts
                JOIN memory_entries AS m ON m.memory_id = memory_entries_fts.memory_id
                WHERE memory_entries_fts MATCH ?
                  AND m.owner_user_id = ?
                  AND (m.expires_at IS NULL OR m.expires_at > ?)
                  AND (
                      ? IS NULL
                      OR m.memory_type IN (SELECT value FROM json_each(?))
                  )
                ORDER BY lexical_rank ASC, m.updated_at DESC, m.memory_id ASC LIMIT ?
                """,
                query_params,
            ).fetchall()

        if not rows:
            return []

        lexical_ranks = [float(row["lexical_rank"]) for row in rows]
        best_rank = min(lexical_ranks)
        worst_rank = max(lexical_ranks)
        rank_span = worst_rank - best_rank
        ranked: list[
            tuple[float, float, float, float, float, str, dict[str, object]]
        ] = []
        for row in rows:
            lexical_rank = float(row["lexical_rank"])
            lexical_score = (
                1.0
                if rank_span <= 1e-12
                else (worst_rank - lexical_rank) / rank_span
            )
            confidence_value = row["confidence"]
            confidence_score = (
                min(1.0, max(0.0, float(confidence_value)))
                if isinstance(confidence_value, (int, float))
                and not isinstance(confidence_value, bool)
                else 0.0
            )
            owner_approval_score = (
                1.0 if row["verification_status"] == "user_approved" else 0.0
            )
            freshness_score = self._freshness_score(row["updated_at"], now)
            total_score = (
                0.70 * lexical_score
                + 0.15 * confidence_score
                + 0.10 * owner_approval_score
                + 0.05 * freshness_score
            )
            record = self._record(row)
            record["retrieval"] = {
                "scheme": "hybrid_fts5_owner_attestation_freshness_v1",
                "score": round(total_score, 6),
                "signals": {
                    "lexical": round(lexical_score, 6),
                    "confidence": round(confidence_score, 6),
                    "owner_approved": round(owner_approval_score, 6),
                    "freshness": round(freshness_score, 6),
                },
            }
            try:
                updated = datetime.fromisoformat(str(row["updated_at"]))
                updated_timestamp = (
                    updated.astimezone(UTC).timestamp()
                    if updated.tzinfo is not None and updated.utcoffset() is not None
                    else 0.0
                )
            except ValueError:
                updated_timestamp = 0.0
            ranked.append(
                (
                    total_score,
                    lexical_score,
                    confidence_score,
                    owner_approval_score,
                    updated_timestamp,
                    str(row["memory_id"]),
                    record,
                )
            )

        ranked.sort(
            key=lambda item: (
                -item[0],
                -item[1],
                -item[2],
                -item[3],
                -item[4],
                item[5],
            )
        )
        return [item[6] for item in ranked[:bounded_limit]]

    def export(self, owner_user_id: str) -> dict[str, object]:
        """Export all owned entries, including expired records, for user-controlled cleanup."""
        with self.tasks._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM memory_entries WHERE owner_user_id = ? ORDER BY created_at ASC",
                (owner_user_id,),
            ).fetchall()
        return {
            "export_version": 1,
            "exported_at": self._now(),
            "entries": [self._record(row) for row in rows],
        }
