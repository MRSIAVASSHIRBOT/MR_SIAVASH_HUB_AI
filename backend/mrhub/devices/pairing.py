"""Owner-scoped one-time device pairing, short-lived credentials, and revocation."""
from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4


class DevicePairingError(ValueError):
    """Raised when a device pairing or credential operation is invalid."""


@dataclass(frozen=True, slots=True)
class DeviceIdentity:
    owner_user_id: str
    device_id: str
    platform: str
    label: str
    scopes: frozenset[str]


class DevicePairingRepository:
    ALLOWED_SCOPES = frozenset({
        "device.heartbeat",
        "screen.capture",
        "app.launch",
        "ui.inspect",
        "ui.interact",
        "browser.read",
        "browser.interact",
        "files.read_scoped",
    })
    ACCESS_TTL_SECONDS = 15 * 60
    REFRESH_TTL_SECONDS = 30 * 24 * 60 * 60
    CHALLENGE_TTL_SECONDS = 5 * 60

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
    def _audit(connection: sqlite3.Connection, *, event_type: str, owner_user_id: str, device_id: str, actor_type: str) -> None:
        connection.execute(
            """INSERT INTO audit_events (
                event_id,event_type,outcome,subject_type,subject_id,
                actor_type,actor_id,created_at,metadata_json
            ) VALUES (?,?,?,?,?,?,?,?,?)""",
            (str(uuid4()),event_type,"success","personal_device",device_id,
             actor_type,owner_user_id,datetime.now(UTC).isoformat(),"{}"),
        )

    def create_challenge(
        self, *, owner_user_id: str, device_id: str, platform: str, label: str,
        advertised_capabilities: tuple[str, ...], scopes: frozenset[str],
    ) -> tuple[str, datetime]:
        try:
            parsed_id = UUID(device_id)
        except ValueError as exc:
            raise DevicePairingError("Device identifier must be a UUID") from exc
        if str(parsed_id) != device_id.lower() or not owner_user_id:
            raise DevicePairingError("Device pairing identity is invalid")
        if platform not in {"windows", "android", "browser"} or not 1 <= len(label.strip()) <= 64:
            raise DevicePairingError("Device platform or label is invalid")
        if not scopes or not scopes.issubset(self.ALLOWED_SCOPES):
            raise DevicePairingError("Requested device scopes are invalid")
        now = self._now()
        expires_at = now + timedelta(seconds=self.CHALLENGE_TTL_SECONDS)
        code = secrets.token_urlsafe(32)
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT 1 FROM personal_devices WHERE device_id=?",
                (device_id,),
            ).fetchone()
            if existing is not None:
                raise DevicePairingError("This device identifier has already been registered")
            pending = connection.execute(
                """SELECT expires_at FROM personal_device_pairing_challenges
                   WHERE device_id=? AND consumed_at IS NULL""",
                (device_id,),
            ).fetchone()
            if pending is not None and pending["expires_at"] > now.isoformat():
                raise DevicePairingError("A pairing challenge for this device is already pending")
            connection.execute(
                "DELETE FROM personal_device_pairing_challenges WHERE device_id=?",
                (device_id,),
            )
            connection.execute(
                """INSERT INTO personal_device_pairing_challenges (
                    challenge_hash,owner_user_id,device_id,platform,label,
                    advertised_capabilities_json,scopes_json,expires_at,created_at,consumed_at
                ) VALUES (?,?,?,?,?,?,?,?,?,NULL)""",
                (self._hash(code),owner_user_id,device_id,platform,label.strip(),
                 json.dumps(sorted(set(advertised_capabilities)),separators=(",",":")),
                 json.dumps(sorted(scopes),separators=(",",":")),expires_at.isoformat(),now.isoformat()),
            )
        return code, expires_at

    def exchange(self, *, pairing_code: str, device_id: str, agent_version: str, os_version: str) -> dict[str, object]:
        now = self._now()
        access = secrets.token_urlsafe(32)
        refresh = secrets.token_urlsafe(48)
        access_expiry = now + timedelta(seconds=self.ACCESS_TTL_SECONDS)
        refresh_expiry = now + timedelta(seconds=self.REFRESH_TTL_SECONDS)
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            challenge = connection.execute(
                "SELECT * FROM personal_device_pairing_challenges WHERE challenge_hash=?",
                (self._hash(pairing_code),),
            ).fetchone()
            if (challenge is None or challenge["consumed_at"] is not None
                or challenge["expires_at"] <= now.isoformat() or challenge["device_id"] != device_id):
                raise DevicePairingError("Pairing code is invalid, expired, or already used")
            consumed = connection.execute(
                "UPDATE personal_device_pairing_challenges SET consumed_at=? WHERE challenge_hash=? AND consumed_at IS NULL",
                (now.isoformat(),self._hash(pairing_code)),
            )
            if consumed.rowcount != 1:
                raise DevicePairingError("Pairing code has already been used")
            connection.execute(
                """INSERT INTO personal_devices (
                    device_id,owner_user_id,platform,label,agent_version,os_version,
                    advertised_capabilities_json,scopes_json,status,created_at,last_seen_at,revoked_at
                ) VALUES (?,?,?,?,?,?,?,?, 'active', ?, ?, NULL)""",
                (device_id,challenge["owner_user_id"],challenge["platform"],challenge["label"],
                 agent_version,os_version,challenge["advertised_capabilities_json"],
                 challenge["scopes_json"],now.isoformat(),now.isoformat()),
            )
            connection.executemany(
                """INSERT INTO personal_device_tokens (
                    token_hash,device_id,token_type,expires_at,created_at,revoked_at
                ) VALUES (?,?,?,?,?,NULL)""",
                [(self._hash(access),device_id,"access",access_expiry.isoformat(),now.isoformat()),
                 (self._hash(refresh),device_id,"refresh",refresh_expiry.isoformat(),now.isoformat())],
            )
            self._audit(connection,event_type="device.paired",owner_user_id=challenge["owner_user_id"],device_id=device_id,actor_type="device_pairing")
            scopes = json.loads(challenge["scopes_json"])
        return {"device_id":device_id,"access_token":access,"token_type":"bearer",
                "expires_in":self.ACCESS_TTL_SECONDS,"refresh_token":refresh,
                "refresh_expires_in":self.REFRESH_TTL_SECONDS,"scopes":scopes}

    def refresh(self, *, refresh_token: str, device_id: str) -> dict[str, object]:
        now = self._now()
        access = secrets.token_urlsafe(32)
        next_refresh = secrets.token_urlsafe(48)
        access_expiry = now + timedelta(seconds=self.ACCESS_TTL_SECONDS)
        refresh_expiry = now + timedelta(seconds=self.REFRESH_TTL_SECONDS)
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """SELECT t.device_id,t.expires_at,t.revoked_at,d.status,d.scopes_json
                   FROM personal_device_tokens t JOIN personal_devices d ON d.device_id=t.device_id
                   WHERE t.token_hash=? AND t.token_type='refresh'""",
                (self._hash(refresh_token),),
            ).fetchone()
            if (row is None or row["device_id"] != device_id or row["revoked_at"] is not None
                or row["expires_at"] <= now.isoformat() or row["status"] != "active"):
                raise DevicePairingError("Refresh credential is invalid, expired, or revoked")
            updated = connection.execute(
                "UPDATE personal_device_tokens SET revoked_at=? WHERE token_hash=? AND token_type='refresh' AND revoked_at IS NULL",
                (now.isoformat(),self._hash(refresh_token)),
            )
            if updated.rowcount != 1:
                raise DevicePairingError("Refresh credential has already been rotated")
            connection.executemany(
                """INSERT INTO personal_device_tokens (token_hash,device_id,token_type,expires_at,created_at,revoked_at)
                   VALUES (?,?,?,?,?,NULL)""",
                [(self._hash(access),device_id,"access",access_expiry.isoformat(),now.isoformat()),
                 (self._hash(next_refresh),device_id,"refresh",refresh_expiry.isoformat(),now.isoformat())],
            )
            scopes = json.loads(row["scopes_json"])
        return {"device_id":device_id,"access_token":access,"token_type":"bearer",
                "expires_in":self.ACCESS_TTL_SECONDS,"refresh_token":next_refresh,
                "refresh_expires_in":self.REFRESH_TTL_SECONDS,"scopes":scopes}

    def authenticate(self, *, access_token: str, device_id: str) -> DeviceIdentity | None:
        now = self._now().isoformat()
        with self._connection() as connection:
            row = connection.execute(
                """SELECT d.owner_user_id,d.device_id,d.platform,d.label,d.scopes_json,d.status,
                          t.expires_at,t.revoked_at
                   FROM personal_device_tokens t JOIN personal_devices d ON d.device_id=t.device_id
                   WHERE t.token_hash=? AND t.token_type='access'""",
                (self._hash(access_token),),
            ).fetchone()
            if (row is None or row["device_id"] != device_id or row["revoked_at"] is not None
                or row["expires_at"] <= now or row["status"] != "active"):
                return None
            connection.execute("UPDATE personal_devices SET last_seen_at=? WHERE device_id=?",(now,device_id))
        return DeviceIdentity(row["owner_user_id"],row["device_id"],row["platform"],row["label"],
                              frozenset(json.loads(row["scopes_json"])))

    def heartbeat(
        self, *, device_id: str, agent_version: str, runtime_state: str,
        app_uptime_seconds: int, last_task_id: str | None,
    ) -> bool:
        now = self._now().isoformat()
        with self._connection() as connection:
            result = connection.execute(
                """UPDATE personal_devices
                   SET last_seen_at=?,agent_version=?,runtime_state=?,
                       app_uptime_seconds=?,last_task_id=?
                   WHERE device_id=? AND status='active'""",
                (now,agent_version,runtime_state,app_uptime_seconds,last_task_id,device_id),
            )
            return result.rowcount == 1

    def list_devices(self, owner_user_id: str) -> list[dict[str, object]]:
        with self._connection() as connection:
            rows = connection.execute(
                """SELECT device_id,platform,label,agent_version,os_version,
                          advertised_capabilities_json,scopes_json,status,created_at,last_seen_at,revoked_at,
                          runtime_state,app_uptime_seconds,last_task_id
                   FROM personal_devices WHERE owner_user_id=? ORDER BY created_at DESC LIMIT 100""",
                (owner_user_id,),
            ).fetchall()
        return [{"device_id":row["device_id"],"platform":row["platform"],"label":row["label"],
                 "agent_version":row["agent_version"],"os_version":row["os_version"],
                 "advertised_capabilities":json.loads(row["advertised_capabilities_json"]),
                 "granted_scopes":json.loads(row["scopes_json"]),"status":row["status"],
                 "created_at":row["created_at"],"last_seen_at":row["last_seen_at"],"revoked_at":row["revoked_at"],
                 "runtime_state":row["runtime_state"],"app_uptime_seconds":row["app_uptime_seconds"],
                 "last_task_id":row["last_task_id"]}
                for row in rows]

    def revoke(self, *, owner_user_id: str, device_id: str) -> bool:
        now = self._now().isoformat()
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            updated = connection.execute(
                """UPDATE personal_devices SET status='revoked',revoked_at=?
                   WHERE owner_user_id=? AND device_id=? AND status='active'""",
                (now,owner_user_id,device_id),
            )
            if updated.rowcount != 1:
                return False
            connection.execute("UPDATE personal_device_tokens SET revoked_at=? WHERE device_id=? AND revoked_at IS NULL",(now,device_id))
            task_table = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='personal_device_tasks'"
            ).fetchone()
            if task_table is not None:
                from mrhub.devices.tasks import DeviceTaskRepository

                DeviceTaskRepository(self.database_path).revoke_device_tasks(
                    connection, device_id=device_id, now_text=now
                )
            self._audit(connection,event_type="device.revoked",owner_user_id=owner_user_id,device_id=device_id,actor_type="owner")
        return True
