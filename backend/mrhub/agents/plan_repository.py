"""Owner-scoped persistence for encrypted GPI/AWI plan records."""

from __future__ import annotations

import base64
import re
import sqlite3
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

from mrhub.jobs.payload_envelope import (
    ENVELOPE_VERSION,
    MAX_PLAINTEXT_BYTES,
    NONCE_BYTES,
    EncryptedPayload,
)

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
        if (
            not isinstance(owner_user_id, str)
            or not owner_user_id.strip()
            or len(owner_user_id) > 200
        ):
            raise AgentWorkOrderPlanError("Plan owner identifier is invalid")
        if not isinstance(plan_digest, str) or not _DIGEST_PATTERN.fullmatch(plan_digest):
            raise AgentWorkOrderPlanError("Plan digest must be a lowercase SHA-256 hex digest")
        if not isinstance(envelope, EncryptedPayload):
            raise AgentWorkOrderPlanError("Encrypted plan envelope is invalid")
        if (
            not isinstance(envelope.version, int)
            or isinstance(envelope.version, bool)
            or envelope.version != ENVELOPE_VERSION
            or not isinstance(envelope.nonce_b64, str)
            or not isinstance(envelope.ciphertext_b64, str)
            or len(envelope.nonce_b64) != 16
            or not 1 <= len(envelope.ciphertext_b64) <= 1_500_000
        ):
            raise AgentWorkOrderPlanError("Encrypted plan envelope is invalid")
        try:
            nonce = base64.b64decode(
                envelope.nonce_b64.encode("ascii"),
                altchars=b"-_",
                validate=True,
            )
            ciphertext = base64.b64decode(
                envelope.ciphertext_b64.encode("ascii"),
                altchars=b"-_",
                validate=True,
            )
        except (ValueError, UnicodeEncodeError) as exc:
            raise AgentWorkOrderPlanError("Encrypted plan envelope is invalid") from exc
        if (
            len(nonce) != NONCE_BYTES
            or not 16 <= len(ciphertext) <= MAX_PLAINTEXT_BYTES + 16
        ):
            raise AgentWorkOrderPlanError("Encrypted plan envelope is outside supported bounds")
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
        # Opportunistically erase expired ciphertext without an unbounded sweep.
        self.expire_due(limit=100)
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


    def expire_due(self, *, limit: int = 100) -> int:
        """Erase ciphertext for a bounded batch of expired, still-active plans."""
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 500:
            raise AgentWorkOrderPlanError("Expiry sweep limit must be between 1 and 500")

        now_text = self._now().isoformat()
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                """
                UPDATE agent_work_order_plans
                SET status = 'expired', nonce_b64 = 'expired',
                    ciphertext_b64 = 'expired'
                WHERE status = 'active'
                  AND plan_id IN (
                    SELECT plan_id
                    FROM agent_work_order_plans
                    WHERE status = 'active' AND expires_at <= ?
                    ORDER BY expires_at, plan_id
                    LIMIT ?
                  )
                """,
                (now_text, limit),
            )
            # Consumed plans keep their workflow foreign key for audit integrity,
            # but their encrypted content still obeys the original plan TTL.
            consumed = connection.execute(
                """
                UPDATE agent_work_order_plans
                SET nonce_b64 = 'expired', ciphertext_b64 = 'expired'
                WHERE status = 'consumed'
                  AND ciphertext_b64 != 'expired'
                  AND plan_id IN (
                    SELECT plan_id
                    FROM agent_work_order_plans
                    WHERE status = 'consumed'
                      AND expires_at <= ?
                      AND ciphertext_b64 != 'expired'
                    ORDER BY expires_at, plan_id
                    LIMIT ?
                  )
                """,
                (now_text, limit),
            )
            return cursor.rowcount + consumed.rowcount


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
        with self._connection() as connection:
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
            nonce_b64 = row["nonce_b64"]
            ciphertext_b64 = row["ciphertext_b64"]
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
                nonce_b64 = "expired"
                ciphertext_b64 = "expired"
            elif (
                status == "consumed"
                and row["expires_at"] <= now_text
                and ciphertext_b64 != "expired"
            ):
                # Retain the one-to-one workflow association while erasing expired
                # ciphertext; status/foreign-key checks remain valid.
                connection.execute(
                    """
                    UPDATE agent_work_order_plans
                    SET nonce_b64 = 'expired', ciphertext_b64 = 'expired'
                    WHERE plan_id = ? AND owner_user_id = ? AND status = 'consumed'
                    """,
                    (normalized_plan_id, owner_user_id),
                )
                nonce_b64 = "expired"
                ciphertext_b64 = "expired"

        return AgentWorkOrderPlanRecord(
            plan_id=row["plan_id"],
            owner_user_id=row["owner_user_id"],
            status=status,
            plan_digest=row["plan_digest"],
            envelope=EncryptedPayload(
                version=row["envelope_version"],
                nonce_b64=nonce_b64,
                ciphertext_b64=ciphertext_b64,
            ),
            created_at=row["created_at"],
            expires_at=row["expires_at"],
            consumed_at=row["consumed_at"],
            workflow_id=row["workflow_id"],
        )

    def revoke(
        self,
        plan_id: str,
        *,
        owner_user_id: str,
    ) -> AgentWorkOrderPlanRecord | None:
        """Revoke an owner's active plan and erase its ciphertext atomically.

        Repeated revocation is idempotent. Expired or consumed records retain
        their terminal state; a foreign owner cannot discover the record.
        """
        try:
            normalized_plan_id = str(UUID(plan_id))
        except (TypeError, ValueError, AttributeError):
            return None
        if normalized_plan_id != plan_id:
            return None
        if not isinstance(owner_user_id, str) or not owner_user_id.strip():
            return None

        now_text = self._now().isoformat()
        with self._connection() as connection:
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
            nonce_b64 = row["nonce_b64"]
            ciphertext_b64 = row["ciphertext_b64"]
            if status == "active":
                status = "expired" if row["expires_at"] <= now_text else "revoked"
                marker = "expired" if status == "expired" else "revoked"
                connection.execute(
                    """
                    UPDATE agent_work_order_plans
                    SET status = ?, nonce_b64 = ?, ciphertext_b64 = ?
                    WHERE plan_id = ? AND owner_user_id = ? AND status = 'active'
                    """,
                    (
                        status,
                        marker,
                        marker,
                        normalized_plan_id,
                        owner_user_id,
                    ),
                )
                nonce_b64 = marker
                ciphertext_b64 = marker

        return AgentWorkOrderPlanRecord(
            plan_id=row["plan_id"],
            owner_user_id=row["owner_user_id"],
            status=status,
            plan_digest=row["plan_digest"],
            envelope=EncryptedPayload(
                version=row["envelope_version"],
                nonce_b64=nonce_b64,
                ciphertext_b64=ciphertext_b64,
            ),
            created_at=row["created_at"],
            expires_at=row["expires_at"],
            consumed_at=row["consumed_at"],
            workflow_id=row["workflow_id"],
        )
