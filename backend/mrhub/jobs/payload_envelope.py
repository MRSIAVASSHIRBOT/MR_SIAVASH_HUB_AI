"""Authenticated encryption for durable workflow input envelopes.

This module deliberately has no plaintext fallback. Callers must supply a
32-byte key from deployment secret management and bind ciphertext to its owner
and workflow identifiers using associated data.
"""
# ruff: noqa: I001
from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from mrhub.config import get_settings


ENVELOPE_VERSION = 1
NONCE_BYTES = 12
KEY_BYTES = 32
MAX_PLAINTEXT_BYTES = 1_048_576


class PayloadEnvelopeError(ValueError):
    """Raised when encrypted workflow payload cannot be safely used."""


@dataclass(frozen=True)
class EncryptedPayload:
    """Versioned envelope fields suitable for durable metadata storage."""

    version: int
    nonce_b64: str
    ciphertext_b64: str


def load_payload_key(encoded_key: str | None = None) -> bytes:
    """Load a 32-byte URL-safe Base64 key; never generate or fall back silently."""
    value = encoded_key if encoded_key is not None else os.getenv("MRH_WORKFLOW_PAYLOAD_KEY")
    if not value:
        configured = get_settings().workflow_payload_key
        value = configured.get_secret_value() if configured is not None else None
    if not value:
        raise PayloadEnvelopeError("Workflow payload encryption key is not configured")
    try:
        key = base64.urlsafe_b64decode(value.encode("ascii") + b"=" * (-len(value) % 4))
    except (ValueError, UnicodeEncodeError) as exc:
        raise PayloadEnvelopeError("Workflow payload encryption key is invalid") from exc
    if len(key) != KEY_BYTES:
        raise PayloadEnvelopeError("Workflow payload encryption key must decode to 32 bytes")
    return key


def _associated_data(*, workflow_id: str, task_id: str, owner_user_id: str) -> bytes:
    fields = (workflow_id, task_id, owner_user_id)
    if any(not isinstance(value, str) or not value.strip() or len(value) > 200 for value in fields):
        raise PayloadEnvelopeError("Workflow payload binding identifiers are invalid")
    return json.dumps(
        {"v": ENVELOPE_VERSION, "workflow_id": workflow_id, "task_id": task_id,
         "owner_user_id": owner_user_id},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def encrypt_payload(
    payload: dict[str, Any],
    *,
    workflow_id: str,
    task_id: str,
    owner_user_id: str,
    key: bytes,
) -> EncryptedPayload:
    """Serialize and encrypt a JSON payload with authenticated resource binding."""
    if len(key) != KEY_BYTES:
        raise PayloadEnvelopeError("Workflow payload encryption key must be 32 bytes")
    try:
        plaintext = json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise PayloadEnvelopeError("Workflow payload must be finite JSON data") from exc
    if len(plaintext) > MAX_PLAINTEXT_BYTES:
        raise PayloadEnvelopeError("Workflow payload exceeds the configured size limit")
    nonce = os.urandom(NONCE_BYTES)
    ciphertext = AESGCM(key).encrypt(
        nonce,
        plaintext,
        _associated_data(
            workflow_id=workflow_id, task_id=task_id, owner_user_id=owner_user_id
        ),
    )
    return EncryptedPayload(
        version=ENVELOPE_VERSION,
        nonce_b64=base64.urlsafe_b64encode(nonce).decode("ascii"),
        ciphertext_b64=base64.urlsafe_b64encode(ciphertext).decode("ascii"),
    )


def decrypt_payload(
    envelope: EncryptedPayload,
    *,
    workflow_id: str,
    task_id: str,
    owner_user_id: str,
    key: bytes,
) -> dict[str, Any]:
    """Decrypt only when version, key, and all associated resource bindings match."""
    if envelope.version != ENVELOPE_VERSION:
        raise PayloadEnvelopeError("Unsupported workflow payload envelope version")
    if len(key) != KEY_BYTES:
        raise PayloadEnvelopeError("Workflow payload encryption key must be 32 bytes")
    try:
        nonce = base64.urlsafe_b64decode(envelope.nonce_b64.encode("ascii"))
        ciphertext = base64.urlsafe_b64decode(envelope.ciphertext_b64.encode("ascii"))
        if len(nonce) != NONCE_BYTES:
            raise PayloadEnvelopeError("Workflow payload nonce is invalid")
        plaintext = AESGCM(key).decrypt(
            nonce,
            ciphertext,
            _associated_data(
                workflow_id=workflow_id, task_id=task_id, owner_user_id=owner_user_id
            ),
        )
        value = json.loads(plaintext.decode("utf-8"))
    except PayloadEnvelopeError:
        raise
    except (ValueError, UnicodeEncodeError, InvalidTag, json.JSONDecodeError) as exc:
        raise PayloadEnvelopeError("Workflow payload authentication failed") from exc
    if not isinstance(value, dict):
        raise PayloadEnvelopeError("Workflow payload must decode to a JSON object")
    return value
