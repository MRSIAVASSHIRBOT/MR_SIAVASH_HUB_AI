"""One-time Telegram pairing and revocable, scoped bot credentials."""

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


class TelegramPairingError(ValueError):
    """Raised when a pairing or credential operation is invalid."""


@dataclass(frozen=True, slots=True)
class TelegramClientIdentity:
    owner_user_id: str
    client_id: str
    telegram_user_id: int
    label: str
    scopes: frozenset[str]


class TelegramPairingRepository:
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
    def _hash(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def create_challenge(
        self,
        *,
        owner_user_id: str,
        telegram_user_id: int,
        client_id: str,
        label: str,
        scopes: frozenset[str],
    ) -> tuple[str, datetime]:
        if telegram_user_id <= 0 or not owner_user_id or not client_id:
            raise TelegramPairingError("Pairing identity is invalid")
        now = self._now()
        expires_at = now + timedelta(seconds=self.CHALLENGE_TTL_SECONDS)
        raw_code = secrets.token_urlsafe(32)
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT status FROM telegram_clients WHERE client_id = ?",
                (client_id,),
            ).fetchone()
            if existing is not None:
                raise TelegramPairingError("This client identifier has already been registered")
            connection.execute(
                """INSERT INTO telegram_pairing_challenges (
                    challenge_hash, owner_user_id, telegram_user_id, client_id,
                    label, scopes_json, expires_at, created_at, consumed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL)""",
                (
                    self._hash(raw_code),
                    owner_user_id,
                    telegram_user_id,
                    client_id,
                    label,
                    json.dumps(sorted(scopes), separators=(",", ":")),
                    expires_at.isoformat(),
                    now.isoformat(),
                ),
            )
        return raw_code, expires_at

    def exchange(
        self, *, pairing_code: str, telegram_user_id: int, client_id: str
    ) -> dict[str, object]:
        now = self._now()
        access_token = secrets.token_urlsafe(32)
        refresh_token = secrets.token_urlsafe(48)
        access_expires = now + timedelta(seconds=self.ACCESS_TTL_SECONDS)
        refresh_expires = now + timedelta(seconds=self.REFRESH_TTL_SECONDS)
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            challenge = connection.execute(
                """SELECT * FROM telegram_pairing_challenges
                   WHERE challenge_hash = ?""",
                (self._hash(pairing_code),),
            ).fetchone()
            if (
                challenge is None
                or challenge["consumed_at"] is not None
                or challenge["expires_at"] <= now.isoformat()
                or challenge["telegram_user_id"] != telegram_user_id
                or challenge["client_id"] != client_id
            ):
                raise TelegramPairingError("Pairing code is invalid, expired, or already used")
            updated = connection.execute(
                """UPDATE telegram_pairing_challenges SET consumed_at = ?
                   WHERE challenge_hash = ? AND consumed_at IS NULL""",
                (now.isoformat(), self._hash(pairing_code)),
            )
            if updated.rowcount != 1:
                raise TelegramPairingError("Pairing code has already been used")
            scopes = json.loads(challenge["scopes_json"])
            connection.execute(
                """INSERT INTO telegram_clients (
                    client_id, owner_user_id, telegram_user_id, label, scopes_json,
                    status, created_at, last_seen_at, revoked_at
                ) VALUES (?, ?, ?, ?, ?, 'active', ?, NULL, NULL)""",
                (
                    client_id,
                    challenge["owner_user_id"],
                    telegram_user_id,
                    challenge["label"],
                    challenge["scopes_json"],
                    now.isoformat(),
                ),
            )
            connection.executemany(
                """INSERT INTO telegram_access_tokens (
                    token_hash, client_id, token_type, expires_at, created_at, revoked_at
                ) VALUES (?, ?, ?, ?, ?, NULL)""",
                [
                    (
                        self._hash(access_token),
                        client_id,
                        "access",
                        access_expires.isoformat(),
                        now.isoformat(),
                    ),
                    (
                        self._hash(refresh_token),
                        client_id,
                        "refresh",
                        refresh_expires.isoformat(),
                        now.isoformat(),
                    ),
                ],
            )
        return {
            "access_token": access_token,
            "token_type": "bearer",
            "expires_in": self.ACCESS_TTL_SECONDS,
            "refresh_token": refresh_token,
            "refresh_expires_in": self.REFRESH_TTL_SECONDS,
            "client_id": client_id,
            "scopes": scopes,
        }

    def refresh(self, *, refresh_token: str, telegram_user_id: int) -> dict[str, object]:
        now = self._now()
        access_token = secrets.token_urlsafe(32)
        access_expires = now + timedelta(seconds=self.ACCESS_TTL_SECONDS)
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """SELECT t.client_id, t.expires_at, t.revoked_at, c.telegram_user_id,
                          c.status, c.scopes_json
                   FROM telegram_access_tokens AS t
                   JOIN telegram_clients AS c ON c.client_id = t.client_id
                   WHERE t.token_hash = ? AND t.token_type = 'refresh'""",
                (self._hash(refresh_token),),
            ).fetchone()
            if (
                row is None
                or row["revoked_at"] is not None
                or row["expires_at"] <= now.isoformat()
                or row["status"] != "active"
                or row["telegram_user_id"] != telegram_user_id
            ):
                raise TelegramPairingError("Refresh credential is invalid, expired, or revoked")
            connection.execute(
                """INSERT INTO telegram_access_tokens (
                    token_hash, client_id, token_type, expires_at, created_at, revoked_at
                ) VALUES (?, ?, 'access', ?, ?, NULL)""",
                (self._hash(access_token), row["client_id"], access_expires.isoformat(), now.isoformat()),
            )
            connection.execute(
                "UPDATE telegram_clients SET last_seen_at = ? WHERE client_id = ?",
                (now.isoformat(), row["client_id"]),
            )
            scopes = json.loads(row["scopes_json"])
        return {
            "access_token": access_token,
            "token_type": "bearer",
            "expires_in": self.ACCESS_TTL_SECONDS,
            "client_id": row["client_id"],
            "scopes": scopes,
        }

    def authenticate(
        self, *, access_token: str, telegram_user_id: int
    ) -> TelegramClientIdentity | None:
        now = self._now().isoformat()
        with self._connection() as connection:
            row = connection.execute(
                """SELECT c.owner_user_id, c.client_id, c.telegram_user_id, c.label,
                          c.scopes_json, c.status, t.expires_at, t.revoked_at
                   FROM telegram_access_tokens AS t
                   JOIN telegram_clients AS c ON c.client_id = t.client_id
                   WHERE t.token_hash = ? AND t.token_type = 'access'""",
                (self._hash(access_token),),
            ).fetchone()
            if (
                row is None
                or row["revoked_at"] is not None
                or row["expires_at"] <= now
                or row["status"] != "active"
                or row["telegram_user_id"] != telegram_user_id
            ):
                return None
            connection.execute(
                "UPDATE telegram_clients SET last_seen_at = ? WHERE client_id = ?",
                (now, row["client_id"]),
            )
        return TelegramClientIdentity(
            owner_user_id=row["owner_user_id"],
            client_id=row["client_id"],
            telegram_user_id=row["telegram_user_id"],
            label=row["label"],
            scopes=frozenset(json.loads(row["scopes_json"])),
        )

    def list_clients(self, owner_user_id: str) -> list[dict[str, object]]:
        with self._connection() as connection:
            rows = connection.execute(
                """SELECT client_id, telegram_user_id, label, scopes_json, status,
                          created_at, last_seen_at, revoked_at
                   FROM telegram_clients WHERE owner_user_id = ?
                   ORDER BY created_at DESC LIMIT 100""",
                (owner_user_id,),
            ).fetchall()
        return [
            {
                "client_id": row["client_id"],
                "telegram_user_id": row["telegram_user_id"],
                "label": row["label"],
                "scopes": json.loads(row["scopes_json"]),
                "status": row["status"],
                "created_at": row["created_at"],
                "last_seen_at": row["last_seen_at"],
                "revoked_at": row["revoked_at"],
            }
            for row in rows
        ]

    def revoke_client(self, *, owner_user_id: str, client_id: str) -> bool:
        now = self._now().isoformat()
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                """UPDATE telegram_clients
                   SET status = 'revoked', revoked_at = ?
                   WHERE owner_user_id = ? AND client_id = ? AND status = 'active'""",
                (now, owner_user_id, client_id),
            )
            if cursor.rowcount != 1:
                return False
            connection.execute(
                """UPDATE telegram_access_tokens SET revoked_at = ?
                   WHERE client_id = ? AND revoked_at IS NULL""",
                (now, client_id),
            )
        return True
