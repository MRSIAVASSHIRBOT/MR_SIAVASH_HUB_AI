"""Encrypted, owner-scoped persistence for resumable workflow inputs.

Raw execution inputs are never stored unless a valid Fernet key is explicitly configured.
Only bounded JSON objects are accepted; sensitive-looking field names are rejected.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet, InvalidToken


class ExecutionInputError(RuntimeError):
    """Base error for workflow execution-input persistence."""


class ExecutionInputUnavailable(ExecutionInputError):
    """Raised when encryption is not configured or stored input cannot be decrypted."""


class ExecutionInputValidationError(ExecutionInputError, ValueError):
    """Raised when input is outside the durable storage policy."""


class WorkflowExecutionInputRepository:
    """Persist encrypted bounded JSON payloads, scoped to the owning user."""

    CURRENT_SCHEMA_VERSION = 1
    MAX_PAYLOAD_BYTES = 64 * 1024
    _SENSITIVE_KEY = re.compile(
        r"(?:password|passwd|secret|api[_-]?key|access[_-]?token|refresh[_-]?token|"
        r"authorization|credential|private[_-]?key|client[_-]?secret)",
        re.IGNORECASE,
    )

    def __init__(self, database_path: Path, encryption_key: str | None) -> None:
        self.database_path = Path(database_path)
        if not encryption_key:
            self._fernet = None
            self._key_id = None
        else:
            try:
                self._fernet = Fernet(encryption_key.encode("ascii"))
            except (ValueError, UnicodeEncodeError) as exc:
                raise ExecutionInputUnavailable("Workflow input encryption key is invalid") from exc
            self._key_id = hashlib.sha256(encryption_key.encode("ascii")).hexdigest()[:16]

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.database_path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _cipher(self) -> Fernet:
        if self._fernet is None or self._key_id is None:
            raise ExecutionInputUnavailable(
                "Workflow execution-input encryption is not configured; refusing plaintext storage"
            )
        return self._fernet

    @classmethod
    def _validate_no_sensitive_keys(cls, value: Any, path: str = "$") -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if not isinstance(key, str):
                    raise ExecutionInputValidationError("Payload object keys must be strings")
                if cls._SENSITIVE_KEY.search(key):
                    raise ExecutionInputValidationError(
                        "Sensitive-looking field is not allowed in durable workflow input: "
                        f"{path}.{key}"
                    )
                cls._validate_no_sensitive_keys(child, f"{path}.{key}")
        elif isinstance(value, list):
            for index, child in enumerate(value):
                cls._validate_no_sensitive_keys(child, f"{path}[{index}]")
        elif value is not None and not isinstance(value, (str, int, float, bool)):
            raise ExecutionInputValidationError("Payload must contain JSON-compatible values")

    @classmethod
    def _encode_payload(cls, payload: dict[str, Any]) -> tuple[bytes, str]:
        if not isinstance(payload, dict):
            raise ExecutionInputValidationError("Workflow input must be a JSON object")
        cls._validate_no_sensitive_keys(payload)
        try:
            encoded = json.dumps(
                payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
            ).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise ExecutionInputValidationError("Workflow input is not valid JSON") from exc
        if len(encoded) > cls.MAX_PAYLOAD_BYTES:
            raise ExecutionInputValidationError("Workflow input exceeds the 64 KiB limit")
        return encoded, hashlib.sha256(encoded).hexdigest()

    @staticmethod
    def _validate_expiry(expires_at: str | None) -> None:
        if expires_at is None:
            return
        try:
            expiry = datetime.fromisoformat(expires_at)
        except (TypeError, ValueError) as exc:
            raise ExecutionInputValidationError(
                "Workflow input expiry must be a valid timezone-aware ISO timestamp"
            ) from exc
        if expiry.tzinfo is None or expiry.utcoffset() is None:
            raise ExecutionInputValidationError(
                "Workflow input expiry must include a timezone"
            )
        if expiry <= datetime.now(UTC):
            raise ExecutionInputValidationError(
                "Workflow input expiry must be in the future"
            )

    def store(
        self,
        workflow_id: str,
        owner_user_id: str,
        payload: dict[str, Any],
        *,
        expires_at: str | None = None,
    ) -> dict[str, str | int]:
        """Encrypt and insert one payload; never overwrite an existing workflow input."""
        if not workflow_id or not owner_user_id:
            raise ExecutionInputValidationError("Workflow and owner identifiers are required")
        self._validate_expiry(expires_at)
        cipher = self._cipher()
        encoded, digest = self._encode_payload(payload)
        ciphertext = cipher.encrypt(encoded)
        now = datetime.now(UTC).isoformat()
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.execute(
                    """INSERT INTO workflow_execution_inputs
                       (workflow_id, owner_user_id, schema_version, key_id,
                        payload_ciphertext, payload_digest, created_at, expires_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        workflow_id, owner_user_id, self.CURRENT_SCHEMA_VERSION,
                        self._key_id, ciphertext, digest, now, expires_at,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise ExecutionInputError(
                    "Workflow input already exists or its owner/workflow reference is invalid"
                ) from exc
        return {
            "workflow_id": workflow_id,
            "schema_version": self.CURRENT_SCHEMA_VERSION,
            "key_id": str(self._key_id),
            "payload_digest": digest,
            "created_at": now,
        }

    def load(self, workflow_id: str, owner_user_id: str) -> dict[str, Any]:
        """Decrypt only for the recorded owner; never expose ciphertext or key material."""
        cipher = self._cipher()
        with self._connection() as connection:
            row = connection.execute(
                """SELECT schema_version, key_id, payload_ciphertext, payload_digest, expires_at
                   FROM workflow_execution_inputs
                   WHERE workflow_id = ? AND owner_user_id = ?""",
                (workflow_id, owner_user_id),
            ).fetchone()
        if row is None:
            raise LookupError("Workflow execution input not found")
        if row["schema_version"] != self.CURRENT_SCHEMA_VERSION or row["key_id"] != self._key_id:
            raise ExecutionInputUnavailable(
                "Workflow input schema or encryption key does not match"
            )
        if row["expires_at"] is not None:
            try:
                expiry = datetime.fromisoformat(row["expires_at"])
            except ValueError as exc:
                raise ExecutionInputUnavailable(
                    "Workflow input expiry metadata is invalid"
                ) from exc
            if expiry.tzinfo is None or expiry <= datetime.now(UTC):
                raise ExecutionInputUnavailable("Workflow input has expired")
        try:
            plaintext = cipher.decrypt(bytes(row["payload_ciphertext"]))
        except (InvalidToken, TypeError, ValueError) as exc:
            raise ExecutionInputUnavailable("Workflow input could not be authenticated") from exc
        if len(plaintext) > self.MAX_PAYLOAD_BYTES:
            raise ExecutionInputUnavailable("Decrypted workflow input exceeds the storage limit")
        if hashlib.sha256(plaintext).hexdigest() != row["payload_digest"]:
            raise ExecutionInputUnavailable("Workflow input integrity check failed")
        try:
            payload = json.loads(plaintext.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ExecutionInputUnavailable("Workflow input payload is invalid") from exc
        if not isinstance(payload, dict):
            raise ExecutionInputUnavailable("Workflow input payload is not an object")
        self._validate_no_sensitive_keys(payload)
        return payload

    def delete(self, workflow_id: str, owner_user_id: str) -> bool:
        """Delete an owner's stored input; this does not delete workflow history."""
        with self._connection() as connection:
            cursor = connection.execute(
                "DELETE FROM workflow_execution_inputs WHERE workflow_id = ? AND owner_user_id = ?",
                (workflow_id, owner_user_id),
            )
            return cursor.rowcount == 1
