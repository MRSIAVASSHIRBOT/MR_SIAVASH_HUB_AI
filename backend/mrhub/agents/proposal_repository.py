"""Owner-scoped persistence for reviewable specialist-agent proposals."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from mrhub.infrastructure.database import TaskRepository


class AgentProposalRepository:
    """Persist candidate definitions without activating them or granting tools."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    def _connect(self) -> sqlite3.Connection:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.database_path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        from mrhub.infrastructure.database import TaskRepository

        TaskRepository(self.database_path).initialize()

    @staticmethod
    def _serialize(row: sqlite3.Row) -> dict[str, object]:
        return {
            "proposal_id": row["proposal_id"],
            "owner_user_id": row["owner_user_id"],
            "name": row["name"],
            "description": row["description"],
            "instructions": row["instructions"],
            "allowed_tools": json.loads(row["allowed_tools_json"]),
            "max_turns": row["max_turns"],
            "rationale": row["rationale"],
            "fingerprint": row["fingerprint"],
            "status": row["status"],
            "created_at": row["created_at"],
            "reviewed_at": row["reviewed_at"],
            "reviewed_by": row["reviewed_by"],
            "activation_state": "inactive",
        }

    def create(
        self,
        proposal_id: UUID,
        owner_user_id: str,
        payload: dict[str, object],
        fingerprint: str,
        audit_event: dict[str, object],
    ) -> dict[str, object]:
        self.initialize()
        created_at = datetime.now(UTC).isoformat()
        try:
            with self._connection() as connection:
                connection.execute(
                    """INSERT INTO agent_proposals (
                        proposal_id, owner_user_id, name, description, instructions,
                        allowed_tools_json, max_turns, rationale, fingerprint,
                        status, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)""",
                    (
                        str(proposal_id),
                        owner_user_id,
                        payload["name"],
                        payload["description"],
                        payload["instructions"],
                        json.dumps(payload["allowed_tools"], ensure_ascii=False),
                        payload["max_turns"],
                        payload["rationale"],
                        fingerprint,
                        created_at,
                    ),
                )
                TaskRepository._insert_audit_event(connection, audit_event)
        except sqlite3.IntegrityError as exc:
            raise ValueError("An active or pending proposal already uses this name") from exc
        result = self.get(proposal_id, owner_user_id=owner_user_id)
        if result is None:
            raise RuntimeError("Created proposal could not be retrieved")
        return result

    def get(self, proposal_id: UUID, *, owner_user_id: str) -> dict[str, object] | None:
        self.initialize()
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM agent_proposals WHERE proposal_id = ? AND owner_user_id = ?",
                (str(proposal_id), owner_user_id),
            ).fetchone()
            TaskRepository._insert_audit_event(connection, audit_event)
        return self._serialize(row) if row is not None else None

    def list(self, *, owner_user_id: str, limit: int = 50) -> list[dict[str, object]]:
        self.initialize()
        bounded_limit = max(1, min(limit, 100))
        with self._connection() as connection:
            rows = connection.execute(
                """SELECT * FROM agent_proposals
                   WHERE owner_user_id = ?
                   ORDER BY created_at DESC, proposal_id DESC LIMIT ?""",
                (owner_user_id, bounded_limit),
            ).fetchall()
        return [self._serialize(row) for row in rows]

    def review(
        self,
        proposal_id: UUID,
        *,
        owner_user_id: str,
        fingerprint: str,
        decision: str,
        audit_event: dict[str, object],
    ) -> dict[str, object] | None:
        if decision not in {"approved", "rejected"}:
            raise ValueError("Unsupported proposal decision")
        self.initialize()
        reviewed_at = datetime.now(UTC).isoformat()
        with self._connection() as connection:
            cursor = connection.execute(
                """UPDATE agent_proposals
                   SET status = ?, reviewed_at = ?, reviewed_by = ?
                   WHERE proposal_id = ? AND owner_user_id = ?
                     AND fingerprint = ? AND status = 'pending'""",
                (
                    decision,
                    reviewed_at,
                    owner_user_id,
                    str(proposal_id),
                    owner_user_id,
                    fingerprint,
                ),
            )
            if cursor.rowcount != 1:
                return None
            row = connection.execute(
                "SELECT * FROM agent_proposals WHERE proposal_id = ? AND owner_user_id = ?",
                (str(proposal_id), owner_user_id),
            ).fetchone()
        return self._serialize(row) if row is not None else None
