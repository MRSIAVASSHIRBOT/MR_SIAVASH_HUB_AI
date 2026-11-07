"""Owner-scoped memory persistence and FTS5 retrieval."""
from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from mrhub.infrastructure.database import TaskRepository


class MemoryRepository:
    """Store explicit memory records and search only the authenticated owner's data."""

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
        memory_id = str(uuid4())
        now = self._now()
        expires_at = self._serialize_expiry(values.get("expires_at"))  # type: ignore[arg-type]
        with self.tasks._connection() as connection:
            connection.execute(
                """
                INSERT INTO memory_entries (
                    memory_id, owner_user_id, scope, category, content, provenance,
                    confidence, verification_status, created_at, updated_at, expires_at
                ) VALUES (?, ?, 'private', ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    memory_id,
                    owner_user_id,
                    values["category"],
                    values["content"],
                    values.get("provenance", "user-authored"),
                    values.get("confidence", 0.7),
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

    def search(
        self, owner_user_id: str, query: str, limit: int = 10
    ) -> list[dict[str, object]]:
        """Run bounded AND-style lexical search with owner/expiry filtering in SQL."""
        terms = re.findall(r"[^\W_]+", query, flags=re.UNICODE)
        if not terms:
            return []
        # Token extraction removes FTS operators and syntax supplied by callers.
        match_expression = " AND ".join(f'"{term.replace(chr(34), chr(34) * 2)}"' for term in terms[:12])
        bounded_limit = max(1, min(limit, 25))
        with self.tasks._connection() as connection:
            rows = connection.execute(
                """
                SELECT m.*
                FROM memory_entries_fts
                JOIN memory_entries AS m ON m.memory_id = memory_entries_fts.memory_id
                WHERE memory_entries_fts MATCH ?
                  AND m.owner_user_id = ?
                  AND (m.expires_at IS NULL OR m.expires_at > ?)
                ORDER BY bm25(memory_entries_fts) ASC, m.updated_at DESC
                LIMIT ?
                """,
                (match_expression, owner_user_id, self._now(), bounded_limit),
            ).fetchall()
        return [self._record(row) for row in rows]

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
