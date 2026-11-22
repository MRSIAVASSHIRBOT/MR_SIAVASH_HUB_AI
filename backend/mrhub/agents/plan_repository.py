"""Owner-scoped persistence for encrypted GPI/AWI plan records."""

from __future__ import annotations

import re
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from collections.abc import Iterator
from typing import Callable
from uuid import UUID

from mrhub.jobs.payload_envelope import EncryptedPayload

MIN_PLAN_TTL_SECONDS = 60
MAX_PLAN_TTL_SECONDS = 86_400
_DIGEST_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class AgentWorkOrderPlanError(RuntimeError):
    """Raised when a persisted work-order plan cannot be read or created safely."""


@dataclass(frozen=True)
class AgentWorkOrderPlanRecord:
    """Encrypted plan metadata scoped to one authenticated owner."""

    plan_id: str
    owner_user_id: str
    status: str
    plan_digest: str
    envelope: EncryptedPayload
    created_at: str
    expires_at: str
    consumed_at: str | None
    workflow_id: str | None


class AgentWorkOrderPlanRepository:
    """Persist only ciphertext and bounded metadata; never store plans in plaintext."""

    def __init__(
        self,
        database_path: Path,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.database_path = database_path
        self._clock = clock or (lambda: datetime.now(UTC))

    def _now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None:
            raise AgentWorkOrderPlanError("Plan repository clock must be timezone-aware")
        return value.astimezone(UTC)

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

    def create(
        self,
        *,
        plan_id: str,
        owner_user_id: str,
        plan_digest: str,
        envelope: EncryptedPayload,
        ttl_seconds: int = 900,
    ) -> AgentWorkOrderPlanRecord:
        """Create one short-lived encrypted plan record for its authenticated owner."""
        try:
            normalized_plan_id = str(UUID(plan_id))
        except (TypeError, ValueError, AttributeError) as exc:
            raise AgentWorkOrderPlanError("Plan identifier must be a UUID") from exc
        if normalized_plan_id != plan_id:
            raise AgentWorkOrderPlanError("Plan identifier must use canonical UUID format")
        if not isinstance(owner_user_id, str) or not owner_user_id.strip() or len(owner_user_id) > 200:
            raise AgentWorkOrderPlanError("Plan owner identifier is invalid")
        if not isinstance(plan_digest, str) or not _DIGEST_PATTERN.fullmatch(plan_digest):
            raise AgentWorkOrderPlanError("Plan digest must be a lowercase SHA-256 hex digest")
        if (
            not isinstance(envelope.version, int)
            or isinstance(envelope.version, bool)
            or envelope.version < 1
            or not isinstance(envelope.nonce_b64, str)
            or not 1 <= len(envelope.nonce_b64) <= 64
            or not isinstance(envelope.ciphertext_b64, str)
            or not 1 <= len(envelope.ciphertext_b64) <= 1_500_000
        ):
            raise AgentWorkOrderPlanError("Encrypted plan envelope is invalid")
        if (
            isinstance(ttl_seconds, bool)
            or not isinstance(ttl_seconds, int)
            or not MIN_PLAN_TTL_SECONDS <= ttl_seconds <= MAX_PLAN_TTL_SECONDS
        ):
            raise AgentWorkOrderPlanError("Plan expiry is outside the allowed TTL range")

        now = self._now()
        expiry = now + timedelta(seconds=ttl_seconds)
        created_at = now.isoformat()
        expires_at_text = expiry.isoformat()
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO agent_work_order_plans (
                    plan_id, owner_user_id, status, plan_digest,
                    envelope_version, nonce_b64, ciphertext_b64,
                    created_at, expires_at, consumed_at, workflow_id
                ) VALUES (?, ?, 'active', ?, ?, ?, ?, ?, ?, NULL, NULL)
                """,
                (
                    normalized_plan_id,
                    owner_user_id,
                    plan_digest,
                    envelope.version,
                    envelope.nonce_b64,
                    envelope.ciphertext_b64,
                    created_at,
                    expires_at_text,
                ),
            )

        return AgentWorkOrderPlanRecord(
            plan_id=normalized_plan_id,
            owner_user_id=owner_user_id,
            status="active",
            plan_digest=plan_digest,
            envelope=envelope,
            created_at=created_at,
            expires_at=expires_at_text,
            consumed_at=None,
            workflow_id=None,
        )

    def get(
        self,
        plan_id: str,
        *,
        owner_user_id: str,
    ) -> AgentWorkOrderPlanRecord | None:
        """Load one plan only for its owner and persist expiry before returning it."""
        try:
            normalized_plan_id = str(UUID(plan_id))
        except (TypeError, ValueError, AttributeError):
            return None
        if normalized_plan_id != plan_id:
            return None
        if not isinstance(owner_user_id, str) or not owner_user_id.strip():
            return None

        now = self._now()
        now_text = now.isoformat()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT plan_id, owner_user_id, status, plan_digest,
                       envelope_version, nonce_b64, ciphertext_b64,
                       created_at, expires_at, consumed_at, workflow_id
                FROM agent_work_order_plans
                WHERE plan_id = ? AND owner_user_id = ?
                """,
                (normalized_plan_id, owner_user_id),
            ).fetchone()
            if row is None:
                return None

            status = row["status"]
            if status == "active" and row["expires_at"] <= now_text:
                connection.execute(
                    """
                    UPDATE agent_work_order_plans
                    SET status = 'expired', nonce_b64 = 'expired',
                        ciphertext_b64 = 'expired'
                    WHERE plan_id = ? AND owner_user_id = ? AND status = 'active'
                    """,
                    (normalized_plan_id, owner_user_id),
                )
                status = "expired"

        return AgentWorkOrderPlanRecord(
            plan_id=row["plan_id"],
            owner_user_id=row["owner_user_id"],
            status=status,
            plan_digest=row["plan_digest"],
            envelope=EncryptedPayload(
                version=row["envelope_version"],
                nonce_b64=row["nonce_b64"],
                ciphertext_b64=row["ciphertext_b64"],
            ),
            created_at=row["created_at"],
            expires_at=row["expires_at"],
            consumed_at=row["consumed_at"],
            workflow_id=row["workflow_id"],
        )
