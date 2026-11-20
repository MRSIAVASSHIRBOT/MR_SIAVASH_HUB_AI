"""Owner-scoped, bounded dispatch of allow-listed tasks to paired devices."""

from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4


class DeviceTaskError(ValueError):
    """Base error for invalid device task operations."""


class DeviceTaskNotFound(DeviceTaskError):
    """The device or task is not owned by the authenticated owner."""


class DeviceTaskPermissionError(DeviceTaskError):
    """The device has not been granted the required action scope."""


class DeviceTaskConflict(DeviceTaskError):
    """The requested task transition is not valid in its current state."""


class DeviceTaskRepository:
    """Persist only bounded task metadata; never persist credentials or raw output."""

    MAX_PENDING_PER_DEVICE = 100
    MAX_SCHEDULE_AHEAD_SECONDS = 30 * 24 * 60 * 60

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

    @staticmethod
    def _now() -> datetime:
        return datetime.now(UTC)

    @staticmethod
    def _hash(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    @staticmethod
    def _digest(value: dict[str, object]) -> str:
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    @staticmethod
    def _serialize(row: sqlite3.Row) -> dict[str, object]:
        parameters = json.loads(row["parameters_json"])
        status = row["status"]
        return {
            "task_id": row["task_id"],
            "device_id": row["device_id"],
            "action": row["action"],
            "app": parameters.get("app"),
            "required_scope": row["required_scope"],
            "status": status,
            "created_at": row["created_at"],
            "scheduled_at": row["scheduled_at"],
            "expires_at": row["expires_at"],
            "attempt_count": row["attempt_count"],
            "timeout_seconds": row["timeout_seconds"],
            "duration_ms": row["duration_ms"],
            "error_code": row["error_code"],
            "outcome_verified": False if status in {"reported_succeeded", "reported_failed"} else None,
            "owner_confirmed": bool(row["owner_confirmed"]),
        }

    @staticmethod
    def _audit(
        connection: sqlite3.Connection,
        *,
        event_type: str,
        outcome: str,
        task_id: str,
        owner_user_id: str,
        actor_type: str,
        actor_id: str,
        action: str,
        required_scope: str,
        reason_code: str,
    ) -> None:
        metadata = json.dumps(
            {
                "correlation_id": task_id,
                "action": action,
                "required_scope": required_scope,
                "reason_code": reason_code,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        connection.execute(
            """INSERT INTO audit_events (
                event_id,event_type,outcome,subject_type,subject_id,
                actor_type,actor_id,created_at,metadata_json
            ) VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                str(uuid4()), event_type, outcome, "device_task", task_id,
                actor_type, actor_id, datetime.now(UTC).isoformat(), metadata,
            ),
        )

    def _reconcile(self, connection: sqlite3.Connection, *, device_id: str, now_text: str) -> None:
        expired_queued = connection.execute(
            """SELECT task_id,action,required_scope FROM personal_device_tasks
               WHERE device_id=? AND status='queued' AND expires_at<=?""",
            (device_id, now_text),
        ).fetchall()
        for row in expired_queued:
            connection.execute(
                """UPDATE personal_device_tasks
                   SET status='expired',updated_at=?,completed_at=?
                   WHERE task_id=? AND status='queued'""",
                (now_text, now_text, row["task_id"]),
            )
            self._audit(
                connection,
                event_type="device.task_expired",
                outcome="expired",
                task_id=row["task_id"],
                owner_user_id="",
                actor_type="system",
                actor_id="hub",
                action=row["action"],
                required_scope=row["required_scope"],
                reason_code="task_ttl_elapsed",
            )

        expired_claims = connection.execute(
            """SELECT task_id,action,required_scope FROM personal_device_tasks
               WHERE device_id=? AND status='claimed'
                 AND (lease_expires_at<=? OR expires_at<=?)""",
            (device_id, now_text, now_text),
        ).fetchall()
        for row in expired_claims:
            connection.execute(
                """UPDATE personal_device_tasks
                   SET status='unknown_outcome',lease_token_hash=NULL,
                       lease_expires_at=NULL,updated_at=?,completed_at=?
                   WHERE task_id=? AND status='claimed'""",
                (now_text, now_text, row["task_id"]),
            )
            self._audit(
                connection,
                event_type="device.task_unknown_outcome",
                outcome="unknown_outcome",
                task_id=row["task_id"],
                owner_user_id="",
                actor_type="system",
                actor_id="hub",
                action=row["action"],
                required_scope=row["required_scope"],
                reason_code="lease_expired_no_replay",
            )

    def create(
        self,
        *,
        owner_user_id: str,
        device_id: str,
        action: str,
        app: str | None,
        required_scope: str,
        idempotency_key: str,
        owner_confirmed: bool,
        scheduled_at: datetime | None,
        expires_in_seconds: int,
        timeout_seconds: int,
    ) -> tuple[dict[str, object], bool]:
        now = self._now()
        if scheduled_at is None:
            scheduled = now
            digest_scheduled_at = None
        else:
            if scheduled_at.tzinfo is None or scheduled_at.utcoffset() is None:
                raise DeviceTaskError("Scheduled time must include a timezone offset")
            scheduled = scheduled_at.astimezone(UTC)
            digest_scheduled_at = scheduled.isoformat()
        parameters = {"app": app} if app is not None else {}
        request_digest = self._digest(
            {
                "device_id": device_id,
                "action": action,
                "app": app,
                "required_scope": required_scope,
                "owner_confirmed": owner_confirmed,
                "scheduled_at": digest_scheduled_at,
                "expires_in_seconds": expires_in_seconds,
                "timeout_seconds": timeout_seconds,
            }
        )
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            device = connection.execute(
                """SELECT owner_user_id,status,scopes_json
                   FROM personal_devices WHERE device_id=?""",
                (device_id,),
            ).fetchone()
            if device is None or device["owner_user_id"] != owner_user_id:
                raise DeviceTaskNotFound("Active owner device not found")
            if device["status"] != "active":
                raise DeviceTaskNotFound("Active owner device not found")
            if required_scope not in json.loads(device["scopes_json"]):
                raise DeviceTaskPermissionError("Device lacks the required action scope")

            self._reconcile(connection, device_id=device_id, now_text=now.isoformat())
            existing = connection.execute(
                """SELECT * FROM personal_device_tasks
                   WHERE owner_user_id=? AND idempotency_key_hash=?""",
                (owner_user_id, self._hash(idempotency_key)),
            ).fetchone()
            if existing is not None:
                if existing["request_digest"] != request_digest:
                    raise DeviceTaskConflict("Idempotency key was already used for another request")
                return self._serialize(existing), False

            if (
                scheduled < now - timedelta(seconds=30)
                or scheduled > now + timedelta(seconds=self.MAX_SCHEDULE_AHEAD_SECONDS)
            ):
                raise DeviceTaskError("Scheduled time must be now or within the next 30 days")
            expires_at = scheduled + timedelta(seconds=expires_in_seconds)
            if expires_at <= now:
                raise DeviceTaskError("Task expiry must be in the future")
            if action == "screen.capture" and (
                scheduled > now + timedelta(minutes=5) or expires_in_seconds > 300
            ):
                raise DeviceTaskError("Sensitive screenshot tasks must be confirmed for near-term execution")

            pending_count = connection.execute(
                """SELECT COUNT(*) FROM personal_device_tasks
                   WHERE device_id=? AND status IN ('queued','claimed')""",
                (device_id,),
            ).fetchone()[0]
            if pending_count >= self.MAX_PENDING_PER_DEVICE:
                raise DeviceTaskConflict("Device task queue is full")

            task_id = str(uuid4())
            connection.execute(
                """INSERT INTO personal_device_tasks (
                    task_id,owner_user_id,device_id,action,parameters_json,required_scope,
                    status,request_digest,idempotency_key_hash,timeout_seconds,scheduled_at,expires_at,
                    lease_token_hash,lease_expires_at,error_code,duration_ms,owner_confirmed,
                    attempt_count,created_at,updated_at,claimed_at,completed_at
                ) VALUES (?,?,?,?,?,?, 'queued',?,?,?,?,?,NULL,NULL,NULL,NULL,?,0,?,?,NULL,NULL)""",
                (
                    task_id, owner_user_id, device_id, action,
                    json.dumps(parameters, sort_keys=True, separators=(",", ":")),
                    required_scope, request_digest, self._hash(idempotency_key), timeout_seconds,
                    scheduled.isoformat(), expires_at.isoformat(), int(owner_confirmed),
                    now.isoformat(), now.isoformat(),
                ),
            )
            self._audit(
                connection,
                event_type="device.task_submitted",
                outcome="queued",
                task_id=task_id,
                owner_user_id=owner_user_id,
                actor_type="owner",
                actor_id=owner_user_id,
                action=action,
                required_scope=required_scope,
                reason_code=("owner_confirmed_sensitive_action" if owner_confirmed else "owner_submitted"),
            )
            row = connection.execute(
                "SELECT * FROM personal_device_tasks WHERE task_id=?",
                (task_id,),
            ).fetchone()
        return self._serialize(row), True

    def claim(
        self,
        *,
        owner_user_id: str,
        device_id: str,
        granted_scopes: frozenset[str],
    ) -> dict[str, object] | None:
        now = self._now()
        now_text = now.isoformat()
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            device = connection.execute(
                """SELECT status,owner_user_id FROM personal_devices WHERE device_id=?""",
                (device_id,),
            ).fetchone()
            if device is None or device["owner_user_id"] != owner_user_id or device["status"] != "active":
                raise DeviceTaskNotFound("Active paired device not found")

            self._reconcile(connection, device_id=device_id, now_text=now_text)

            active = connection.execute(
                """SELECT 1 FROM personal_device_tasks
                   WHERE device_id=? AND status='claimed' AND lease_expires_at>? LIMIT 1""",
                (device_id, now_text),
            ).fetchone()
            if active is not None:
                return None

            candidates = connection.execute(
                """SELECT * FROM personal_device_tasks
                   WHERE owner_user_id=? AND device_id=? AND status='queued'
                     AND scheduled_at<=? AND expires_at>?
                   ORDER BY scheduled_at ASC,created_at ASC,task_id ASC LIMIT 20""",
                (owner_user_id, device_id, now_text, now_text),
            ).fetchall()
            selected = next(
                (row for row in candidates if row["required_scope"] in granted_scopes),
                None,
            )
            if selected is None:
                return None

            lease_token = secrets.token_urlsafe(32)
            lease_expires = min(
                now + timedelta(seconds=selected["timeout_seconds"]),
                datetime.fromisoformat(selected["expires_at"]),
            )
            updated = connection.execute(
                """UPDATE personal_device_tasks
                   SET status='claimed',lease_token_hash=?,lease_expires_at=?,
                       claimed_at=?,updated_at=?,attempt_count=1
                   WHERE task_id=? AND status='queued' AND attempt_count=0""",
                (
                    self._hash(lease_token), lease_expires.isoformat(),
                    now_text, now_text, selected["task_id"],
                ),
            )
            if updated.rowcount != 1:
                return None
            self._audit(
                connection,
                event_type="device.task_claimed",
                outcome="claimed",
                task_id=selected["task_id"],
                owner_user_id=owner_user_id,
                actor_type="device",
                actor_id=device_id,
                action=selected["action"],
                required_scope=selected["required_scope"],
                reason_code="device_claimed",
            )
            row = connection.execute(
                "SELECT * FROM personal_device_tasks WHERE task_id=?",
                (selected["task_id"],),
            ).fetchone()
        return {
            "task": self._serialize(row),
            "lease_token": lease_token,
            "lease_expires_at": lease_expires.isoformat(),
        }

    def report_outcome(
        self,
        *,
        owner_user_id: str,
        device_id: str,
        task_id: str,
        lease_token: str,
        outcome: str,
        error_code: str | None,
        duration_ms: int,
    ) -> dict[str, object] | None:
        now_text = self._now().isoformat()
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """SELECT * FROM personal_device_tasks
                   WHERE task_id=? AND owner_user_id=? AND device_id=?""",
                (task_id, owner_user_id, device_id),
            ).fetchone()
            if row is None or row["status"] != "claimed":
                return None
            if row["lease_expires_at"] <= now_text:
                connection.execute(
                    """UPDATE personal_device_tasks
                       SET status='unknown_outcome',lease_token_hash=NULL,
                           lease_expires_at=NULL,updated_at=?,completed_at=?
                       WHERE task_id=? AND status='claimed'""",
                    (now_text, now_text, task_id),
                )
                self._audit(
                    connection,
                    event_type="device.task_unknown_outcome",
                    outcome="unknown_outcome",
                    task_id=task_id,
                    owner_user_id=owner_user_id,
                    actor_type="device",
                    actor_id=device_id,
                    action=row["action"],
                    required_scope=row["required_scope"],
                    reason_code="late_outcome_after_lease",
                )
                return None
            if not secrets.compare_digest(row["lease_token_hash"], self._hash(lease_token)):
                return None

            status = "reported_succeeded" if outcome == "succeeded" else "reported_failed"
            connection.execute(
                """UPDATE personal_device_tasks
                   SET status=?,lease_token_hash=NULL,lease_expires_at=NULL,
                       error_code=?,duration_ms=?,updated_at=?,completed_at=?
                   WHERE task_id=? AND status='claimed'""",
                (status, error_code, duration_ms, now_text, now_text, task_id),
            )
            self._audit(
                connection,
                event_type="device.task_outcome_reported",
                outcome=status,
                task_id=task_id,
                owner_user_id=owner_user_id,
                actor_type="device",
                actor_id=device_id,
                action=row["action"],
                required_scope=row["required_scope"],
                reason_code=error_code or "device_reported_success",
            )
            updated = connection.execute(
                "SELECT * FROM personal_device_tasks WHERE task_id=?",
                (task_id,),
            ).fetchone()
        return self._serialize(updated)



    def list_for_owner(
        self, *, owner_user_id: str, device_id: str, limit: int = 100
    ) -> list[dict[str, object]]:
        bounded_limit = max(1, min(limit, 100))
        now_text = self._now().isoformat()
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            device = connection.execute(
                "SELECT 1 FROM personal_devices WHERE owner_user_id=? AND device_id=?",
                (owner_user_id, device_id),
            ).fetchone()
            if device is None:
                raise DeviceTaskNotFound("Device task not found")
            self._reconcile(connection, device_id=device_id, now_text=now_text)
            rows = connection.execute(
                """SELECT * FROM personal_device_tasks
                   WHERE owner_user_id=? AND device_id=?
                   ORDER BY created_at DESC,task_id DESC LIMIT ?""",
                (owner_user_id, device_id, bounded_limit),
            ).fetchall()
        return [self._serialize(row) for row in rows]

    def get_for_owner(
        self, *, owner_user_id: str, device_id: str, task_id: str
    ) -> dict[str, object] | None:
        now_text = self._now().isoformat()
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            device = connection.execute(
                "SELECT 1 FROM personal_devices WHERE owner_user_id=? AND device_id=?",
                (owner_user_id, device_id),
            ).fetchone()
            if device is None:
                return None
            self._reconcile(connection, device_id=device_id, now_text=now_text)
            row = connection.execute(
                """SELECT * FROM personal_device_tasks
                   WHERE owner_user_id=? AND device_id=? AND task_id=?""",
                (owner_user_id, device_id, task_id),
            ).fetchone()
        return self._serialize(row) if row is not None else None

    def cancel_for_owner(
        self, *, owner_user_id: str, device_id: str, task_id: str
    ) -> dict[str, object] | None:
        now_text = self._now().isoformat()
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            device = connection.execute(
                "SELECT 1 FROM personal_devices WHERE owner_user_id=? AND device_id=?",
                (owner_user_id, device_id),
            ).fetchone()
            if device is None:
                return None
            self._reconcile(connection, device_id=device_id, now_text=now_text)
            row = connection.execute(
                """SELECT * FROM personal_device_tasks
                   WHERE owner_user_id=? AND device_id=? AND task_id=?""",
                (owner_user_id, device_id, task_id),
            ).fetchone()
            if row is None:
                return None
            if row["status"] != "queued":
                raise DeviceTaskConflict("Only queued device tasks can be cancelled safely")
            connection.execute(
                """UPDATE personal_device_tasks
                   SET status='cancelled',updated_at=?,completed_at=?
                   WHERE task_id=? AND status='queued'""",
                (now_text, now_text, task_id),
            )
            self._audit(
                connection,
                event_type="device.task_cancelled",
                outcome="cancelled",
                task_id=task_id,
                owner_user_id=owner_user_id,
                actor_type="owner",
                actor_id=owner_user_id,
                action=row["action"],
                required_scope=row["required_scope"],
                reason_code="owner_cancelled_before_claim",
            )
            updated = connection.execute(
                "SELECT * FROM personal_device_tasks WHERE task_id=?",
                (task_id,),
            ).fetchone()
        return self._serialize(updated)

    def revoke_device_tasks(
        self,
        connection: sqlite3.Connection,
        *,
        device_id: str,
        now_text: str,
        actor_type: str = "owner",
        actor_id: str | None = None,
    ) -> None:
        """Cancel queued work and fence claimed work after device revocation."""
        rows = connection.execute(
            """SELECT task_id,owner_user_id,action,required_scope,status
               FROM personal_device_tasks
               WHERE device_id=? AND status IN ('queued','claimed')""",
            (device_id,),
        ).fetchall()
        for row in rows:
            next_status = "cancelled" if row["status"] == "queued" else "unknown_outcome"
            reason_code = (
                "device_revoked_before_claim"
                if next_status == "cancelled"
                else "device_revoked_after_claim"
            )
            connection.execute(
                """UPDATE personal_device_tasks
                   SET status=?,lease_token_hash=NULL,lease_expires_at=NULL,
                       updated_at=?,completed_at=?
                   WHERE task_id=? AND status IN ('queued','claimed')""",
                (next_status, now_text, now_text, row["task_id"]),
            )
            self._audit(
                connection,
                event_type=(
                    "device.task_cancelled"
                    if next_status == "cancelled"
                    else "device.task_unknown_outcome"
                ),
                outcome=next_status,
                task_id=row["task_id"],
                owner_user_id=row["owner_user_id"],
                actor_type=actor_type,
                actor_id=actor_id if actor_id is not None else row["owner_user_id"],
                action=row["action"],
                required_scope=row["required_scope"],
                reason_code=reason_code,
            )

