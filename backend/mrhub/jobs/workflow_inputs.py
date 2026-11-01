"""Authenticated encryption and owner-scoped persistence for workflow execution inputs.

Executable request payloads are never stored as plaintext. The encryption key must be
provided out of band via MRH_WORKFLOW_INPUT_ENCRYPTION_KEY as URL-safe base64 for
exactly 32 bytes. Rotating keys requires retaining the old key for existing rows.
"""
from __future__ import annotations

import base64
import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class WorkflowInputError(RuntimeError):
    """Raised when encrypted workflow inputs cannot safely be stored or read."""


class WorkflowInputCipher:
    """AES-256-GCM codec with authenticated workflow/owner/schema metadata."""

    SCHEMA_VERSION = 1
    NONCE_BYTES = 12

    def __init__(self, encoded_key: str) -> None:
        try:
            key = base64.urlsafe_b64decode(encoded_key.encode("ascii") + b"=" * (-len(encoded_key) % 4))
        except (ValueError, UnicodeEncodeError) as exc:
            raise WorkflowInputError("Workflow input encryption key must be URL-safe base64") from exc
        if len(key) != 32:
            raise WorkflowInputError("Workflow input encryption key must decode to exactly 32 bytes")
        self._aes = AESGCM(key)
        self.key_id = hashlib.sha256(key).hexdigest()[:16]

    @classmethod
    def generate_key(cls) -> str:
        """Generate a URL-safe 32-byte key for secure deployment-time provisioning."""
        return base64.urlsafe_b64encode(AESGCM.generate_key(bit_length=256)).decode("ascii").rstrip("=")

    @staticmethod
    def _aad(workflow_id: str, owner_user_id: str, schema_version: int, key_id: str) -> bytes:
        return json.dumps(
            [workflow_id, owner_user_id, schema_version, key_id],
            separators=(",", ":"),
        ).encode("utf-8")

    def encrypt(self, workflow_id: UUID | str, owner_user_id: str, payload: dict[str, Any]) -> tuple[bytes, str]:
        workflow = str(workflow_id)
        try:
            plaintext = json.dumps(
                payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
            ).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise WorkflowInputError("Workflow inputs must be JSON-serializable") from exc
        nonce = __import__("os").urandom(self.NONCE_BYTES)
        aad = self._aad(workflow, owner_user_id, self.SCHEMA_VERSION, self.key_id)
        ciphertext = nonce + self._aes.encrypt(nonce, plaintext, aad)
        return ciphertext, hashlib.sha256(plaintext).hexdigest()

    def decrypt(
        self,
        workflow_id: UUID | str,
        owner_user_id: str,
        ciphertext: bytes,
        expected_digest: str,
        *,
        schema_version: int = SCHEMA_VERSION,
        key_id: str | None = None,
    ) -> dict[str, Any]:
        workflow = str(workflow_id)
        actual_key_id = key_id or self.key_id
        if schema_version != self.SCHEMA_VERSION or actual_key_id != self.key_id:
            raise WorkflowInputError("No configured key supports this workflow input version")
        if len(ciphertext) <= self.NONCE_BYTES:
            raise WorkflowInputError("Encrypted workflow input is truncated")
        nonce, encrypted = ciphertext[: self.NONCE_BYTES], ciphertext[self.NONCE_BYTES :]
        aad = self._aad(workflow, owner_user_id, schema_version, actual_key_id)
        try:
            plaintext = self._aes.decrypt(nonce, encrypted, aad)
        except InvalidTag as exc:
            raise WorkflowInputError("Workflow input authentication failed") from exc
        if not hashlib.sha256(plaintext).hexdigest() == expected_digest:
            raise WorkflowInputError("Workflow input integrity check failed")
        try:
            value = json.loads(plaintext)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise WorkflowInputError("Decrypted workflow input is not valid JSON") from exc
        if not isinstance(value, dict):
            raise WorkflowInputError("Workflow input root must be an object")
        return value


class WorkflowInputRepository:
    """Persist ciphertext only; callers must initialize the database migrations first."""

    def __init__(self, database_path: Path, cipher: WorkflowInputCipher) -> None:
        self.database_path = Path(database_path)
        self.cipher = cipher

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=5.0)
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    def save(
        self,
        workflow_id: UUID | str,
        owner_user_id: str,
        payload: dict[str, Any],
        *,
        expires_at: str | None = None,
    ) -> None:
        workflow = str(workflow_id)
        ciphertext, digest = self.cipher.encrypt(workflow, owner_user_id, payload)
        created_at = datetime.now(UTC).isoformat()
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO workflow_execution_inputs
                   (workflow_id, owner_user_id, schema_version, key_id,
                    payload_ciphertext, payload_digest, created_at, expires_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(workflow_id) DO UPDATE SET
                     owner_user_id = excluded.owner_user_id,
                     schema_version = excluded.schema_version,
                     key_id = excluded.key_id,
                     payload_ciphertext = excluded.payload_ciphertext,
                     payload_digest = excluded.payload_digest,
                     created_at = excluded.created_at,
                     expires_at = excluded.expires_at""",
                (workflow, owner_user_id, self.cipher.SCHEMA_VERSION, self.cipher.key_id,
                 ciphertext, digest, created_at, expires_at),
            )

    def load(self, workflow_id: UUID | str, owner_user_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                """SELECT schema_version, key_id, payload_ciphertext, payload_digest, expires_at
                   FROM workflow_execution_inputs
                   WHERE workflow_id = ? AND owner_user_id = ?""",
                (str(workflow_id), owner_user_id),
            ).fetchone()
        if row is None:
            raise LookupError("Workflow inputs not found")
        if row[4] is not None and row[4] <= datetime.now(UTC).isoformat():
            raise LookupError("Workflow inputs have expired")
        return self.cipher.decrypt(
            workflow_id, owner_user_id, bytes(row[2]), row[3],
            schema_version=row[0], key_id=row[1],
        )

    def delete(self, workflow_id: UUID | str, owner_user_id: str) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM workflow_execution_inputs WHERE workflow_id = ? AND owner_user_id = ?",
                (str(workflow_id), owner_user_id),
            )
            return cursor.rowcount == 1
