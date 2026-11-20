"""Owner-authorized, idempotent, bounded device task dispatch."""
from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4


class DeviceTaskError(ValueError):
    """Raised when a device task violates owner, scope, or lifecycle policy."""


ALLOWED_APP_ALIASES = frozenset({"notepad", "calculator", "explorer", "browser", "chatgpt"})
SUCCESS_CODES = frozenset({"launched"})
FAILURE_CODES = frozenset({"launch_failed", "app_not_available", "unsupported_platform"})
LEASE_SECONDS = 60
MAX_SCHEDULE_AHEAD_SECONDS = 30 * 24 * 60 * 60


class DeviceTaskRepository:
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
    def _reconcile(connection: sqlite3.Connection, *, device_id: str, now_text: str) -> None:
        connection.execute(
            """UPDATE personal_device_tasks
               SET status='expired',completed_at=?,result_code='expired'
               WHERE device_id=? AND status='queued' AND expires_at<=?""",
            (now_text, device_id, now_text),
        )
        connection.execute(
            """UPDATE personal_device_tasks
               SET status='delivery_unknown',completed_at=?,result_code='delivery_unknown'
               WHERE device_id=? AND status='claimed'
                 AND (lease_expires_at<=? OR expires_at<=?)""",
            (now_text, device_id, now_text, now_text),
        )

    @staticmethod
    def _audit(
        connection: sqlite3.Connection,
        *,
        event_type: str,
        outcome: str,
        owner_user_id: str,
        device_id: str,
        actor_type: str,
        actor_id: str,
        task_id: str,
        metadata: dict[str, object],
    ) -> None:
        connection.execute(
            """INSERT INTO audit_events (
                event_id,event_type,outcome,subject_type,subject_id,
                actor_type,actor_id,created_at,metadata_json
            ) VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                str(uuid4()), event_type, outcome, "personal_device_task", task_id,
                actor_type, actor_id, datetime.now(UTC).isoformat(),
                json.dumps({"owner_user_id": owner_user_id, **metadata}, separators=(",", ":"), sort_keys=True),
            ),
        )

    @staticmethod
    def _serialize(row: sqlite3.Row) -> dict[str, object]:
        payload = json.loads(row["payload_json"])
        return {
            "task_id": row["task_id"],
            "device_id": row["device_id"],
            "action": row["action"],
            "app_alias": payload["app_alias"],
            "status": row["status"],
            "idempotency_key": row["idempotency_key"],
            "created_at": row["created_at"],
            "scheduled_at": row["available_at"],
            "expires_at": row["expires_at"],
            "claimed_at": row["claimed_at"],
            "lease_expires_at": row["lease_expires_at"],
            "completed_at": row["completed_at"],
            "result_code": row["result_code"],
            "attempt_count": row["attempt_count"],
        }

    def create_owner_task(
        self,
        *,
        owner_user_id: str,
        device_id: str,
        app_alias: str,
        idempotency_key: str,
        scheduled_at: datetime,
        expires_in_seconds: int = 300,
    ) -> dict[str, object]:
        try:
            task_key = str(UUID(idempotency_key))
        except (ValueError, TypeError) as exc:
            raise DeviceTaskError("Idempotency key must be a UUID") from exc
        try:
            canonical_device_id = str(UUID(device_id))
        except (ValueError, TypeError) as exc:
            raise DeviceTaskError("Device identifier is invalid") from exc
        if canonical_device_id != device_id.lower():
            raise DeviceTaskError("Device identifier is invalid")
        if not owner_user_id or app_alias not in ALLOWED_APP_ALIASES:
            raise DeviceTaskError("Owner or application alias is invalid")
        if (
            isinstance(expires_in_seconds, bool)
            or not isinstance(expires_in_seconds, int)
            or not 30 <= expires_in_seconds <= 86_400
        ):
            raise DeviceTaskError("Task expiry must be between 30 and 86400 seconds")
        if scheduled_at.tzinfo is None or scheduled_at.utcoffset() is None:
            raise DeviceTaskError("Scheduled time must include a timezone offset")

        now = self._now()
        scheduled = scheduled_at.astimezone(UTC)
        if scheduled < now - timedelta(seconds=30) or scheduled > now + timedelta(seconds=MAX_SCHEDULE_AHEAD_SECONDS):
            raise DeviceTaskError("Scheduled time must be now or within the next 30 days")
        expires = scheduled + timedelta(seconds=expires_in_seconds)
        if expires <= now:
            raise DeviceTaskError("Task expiry must be in the future")

        task_id = str(uuid4())
        created_at = now.isoformat()
        available_at = scheduled.isoformat()
        expires_at = expires.isoformat()
        payload_json = json.dumps({"app_alias": app_alias}, separators=(",", ":"), sort_keys=True)

        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            device = connection.execute(
                "SELECT status,scopes_json FROM personal_devices WHERE owner_user_id=? AND device_id=?",
                (owner_user_id, device_id),
            ).fetchone()
            if device is None or device["status"] != "active":
                raise DeviceTaskError("Active owner device not found")
            if "app.launch" not in json.loads(device["scopes_json"]):
                raise DeviceTaskError("Device does not have the app.launch scope")
            self._reconcile(connection, device_id=device_id, now_text=now.isoformat())

            existing = connection.execute(
                """SELECT * FROM personal_device_tasks
                   WHERE owner_user_id=? AND device_id=? AND idempotency_key=?""",
                (owner_user_id, device_id, task_key),
            ).fetchone()
            if existing is not None:
                if (
                    existing["action"] != "launch_app"
                    or existing["payload_json"] != payload_json
                    or existing["available_at"] != available_at
                    or existing["expires_at"] != expires_at
                ):
                    raise DeviceTaskError("Idempotency key was already used for different task data")
                return self._serialize(existing)

            pending_count = connection.execute(
                """SELECT COUNT(*) FROM personal_device_tasks
                   WHERE device_id=? AND status IN ('queued','claimed')""",
                (device_id,),
            ).fetchone()[0]
            if pending_count >= 100:
                raise DeviceTaskError("Device task queue is full; wait for pending tasks to finish")

            connection.execute(
                """INSERT INTO personal_device_tasks (
                    task_id,owner_user_id,device_id,action,payload_json,idempotency_key,
                    status,created_at,available_at,expires_at,claimed_at,lease_expires_at,
                    completed_at,result_code,attempt_count
                ) VALUES (?,?,?,?,?,?,'queued',?,?,?,NULL,NULL,NULL,NULL,0)""",
                (
                    task_id, owner_user_id, device_id, "launch_app", payload_json,
                    task_key, created_at, available_at, expires_at,
                ),
            )
            self._audit(
                connection,
                event_type="device.task_created",
                outcome="success",
                owner_user_id=owner_user_id,
                device_id=device_id,
                actor_type="owner",
                actor_id=owner_user_id,
                task_id=task_id,
                metadata={"action": "launch_app", "app_alias": app_alias},
            )
            row = connection.execute(
                "SELECT * FROM personal_device_tasks WHERE task_id=?",
                (task_id,),
            ).fetchone()
        return self._serialize(row)

    def claim_next(self, *, owner_user_id: str, device_id: str) -> dict[str, object] | None:
        now = self._now()
        now_text = now.isoformat()
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._reconcile(connection, device_id=device_id, now_text=now_text)
            row = connection.execute(
                """SELECT t.* FROM personal_device_tasks t
                   JOIN personal_devices d ON d.device_id=t.device_id
                   WHERE t.owner_user_id=? AND t.device_id=? AND d.status='active'
                     AND t.status='queued' AND t.available_at<=? AND t.expires_at>?
                   ORDER BY t.available_at,t.created_at,t.task_id LIMIT 1""",
                (owner_user_id, device_id, now_text, now_text),
            ).fetchone()
            if row is None:
                return None
            lease_expiry = min(now + timedelta(seconds=LEASE_SECONDS), datetime.fromisoformat(row["expires_at"]))
            updated = connection.execute(
                """UPDATE personal_device_tasks
                   SET status='claimed',claimed_at=?,lease_expires_at=?,attempt_count=attempt_count+1
                   WHERE task_id=? AND status='queued'""",
                (now_text, lease_expiry.isoformat(), row["task_id"]),
            )
            if updated.rowcount != 1:
                return None
            self._audit(
                connection,
                event_type="device.task_claimed",
                outcome="success",
                owner_user_id=owner_user_id,
                device_id=device_id,
                actor_type="device",
                actor_id=device_id,
                task_id=row["task_id"],
                metadata={"action": row["action"]},
            )
            claimed = connection.execute(
                "SELECT * FROM personal_device_tasks WHERE task_id=?",
                (row["task_id"],),
            ).fetchone()
        return self._serialize(claimed)

    def complete_device_task(
        self,
        *,
        device_id: str,
        task_id: str,
        outcome: str,
        result_code: str,
    ) -> dict[str, object]:
        try:
            task_uuid = str(UUID(task_id))
        except (ValueError, TypeError) as exc:
            raise DeviceTaskError("Task identifier is invalid") from exc
        if (outcome == "succeeded" and result_code not in SUCCESS_CODES) or (
            outcome == "failed" and result_code not in FAILURE_CODES
        ):
            raise DeviceTaskError("Task outcome or result code is invalid")
        if outcome not in {"succeeded", "failed"}:
            raise DeviceTaskError("Task outcome is invalid")

        now = self._now()
        now_text = now.isoformat()
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """SELECT * FROM personal_device_tasks WHERE task_id=? AND device_id=?""",
                (task_uuid, device_id),
            ).fetchone()
            if row is None:
                raise DeviceTaskError("Task not found for this device")
            if row["status"] != "claimed":
                raise DeviceTaskError("Task is not in a claimable completion state")
            if row["lease_expires_at"] <= now_text or row["expires_at"] <= now_text:
                connection.execute(
                    """UPDATE personal_device_tasks
                       SET status='delivery_unknown',completed_at=?,result_code='delivery_unknown'
                       WHERE task_id=? AND status='claimed'""",
                    (now_text, task_uuid),
                )
                self._audit(
                    connection,
                    event_type="device.task_delivery_unknown",
                    outcome="failure",
                    owner_user_id=row["owner_user_id"],
                    device_id=device_id,
                    actor_type="device",
                    actor_id=device_id,
                    task_id=task_uuid,
                    metadata={"reason_code": "lease_expired"},
                )
                unknown = connection.execute(
                    "SELECT * FROM personal_device_tasks WHERE task_id=?",
                    (task_uuid,),
                ).fetchone()
                return self._serialize(unknown)
            updated = connection.execute(
                """UPDATE personal_device_tasks
                   SET status=?,completed_at=?,result_code=?
                   WHERE task_id=? AND device_id=? AND status='claimed'""",
                (outcome, now_text, result_code, task_uuid, device_id),
            )
            if updated.rowcount != 1:
                raise DeviceTaskError("Task completion was already recorded")
            self._audit(
                connection,
                event_type="device.task_completed",
                outcome=outcome,
                owner_user_id=row["owner_user_id"],
                device_id=device_id,
                actor_type="device",
                actor_id=device_id,
                task_id=task_uuid,
                metadata={"result_code": result_code},
            )
            completed = connection.execute(
                "SELECT * FROM personal_device_tasks WHERE task_id=?",
                (task_uuid,),
            ).fetchone()
        return self._serialize(completed)

    def cancel_owner_task(self, *, owner_user_id: str, device_id: str, task_id: str) -> str | None:
        now = self._now().isoformat()
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._reconcile(
                connection,
                device_id=device_id,
                now_text=now,
            )
            row = connection.execute(
                """SELECT status FROM personal_device_tasks
                   WHERE owner_user_id=? AND device_id=? AND task_id=?""",
                (owner_user_id, device_id, task_id),
            ).fetchone()
            if row is None:
                return None
            if row["status"] != "queued":
                return row["status"]
            updated = connection.execute(
                """UPDATE personal_device_tasks
                   SET status='cancelled',completed_at=?,result_code='cancelled'
                   WHERE owner_user_id=? AND device_id=? AND task_id=? AND status='queued'""",
                (now, owner_user_id, device_id, task_id),
            )
            if updated.rowcount != 1:
                return "changed"
            self._audit(
                connection,
                event_type="device.task_cancelled",
                outcome="success",
                owner_user_id=owner_user_id,
                device_id=device_id,
                actor_type="owner",
                actor_id=owner_user_id,
                task_id=task_id,
                metadata={"reason_code": "owner_cancelled_before_claim"},
            )
            return "cancelled"

    def list_owner_tasks(self, *, owner_user_id: str, device_id: str) -> list[dict[str, object]]:
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._reconcile(
                connection,
                device_id=device_id,
                now_text=self._now().isoformat(),
            )
            rows = connection.execute(
                """SELECT * FROM personal_device_tasks
                   WHERE owner_user_id=? AND device_id=?
                   ORDER BY created_at DESC,task_id DESC LIMIT 100""",
                (owner_user_id, device_id),
            ).fetchall()
        return [self._serialize(row) for row in rows]
