"""Security tests for encrypted workflow payload envelopes."""
# ruff: noqa: I001
import base64

import pytest

from mrhub.jobs.payload_envelope import (
    ENVELOPE_VERSION,
    EncryptedPayload,
    PayloadEnvelopeError,
    decrypt_payload,
    encrypt_payload,
    load_payload_key,
)


KEY = b"k" * 32
BINDING = {
    "workflow_id": "workflow-1",
    "task_id": "task-1",
    "owner_user_id": "user-1",
}


def test_round_trip_preserves_json_payload_and_version() -> None:
    payload = {"request": {"goal": "hello ✨", "tools": []}, "plan_version": 1}
    envelope = encrypt_payload(payload, **BINDING, key=KEY)
    assert envelope.version == ENVELOPE_VERSION
    assert decrypt_payload(envelope, **BINDING, key=KEY) == payload


def test_same_payload_uses_fresh_nonce() -> None:
    first = encrypt_payload({"a": 1}, **BINDING, key=KEY)
    second = encrypt_payload({"a": 1}, **BINDING, key=KEY)
    assert first.nonce_b64 != second.nonce_b64
    assert first.ciphertext_b64 != second.ciphertext_b64


@pytest.mark.parametrize(
    "changed",
    [
        {"workflow_id": "workflow-other"},
        {"task_id": "task-other"},
        {"owner_user_id": "user-other"},
    ],
)
def test_ciphertext_is_bound_to_all_resource_identifiers(changed: dict[str, str]) -> None:
    envelope = encrypt_payload({"private": "value"}, **BINDING, key=KEY)
    binding = {**BINDING, **changed}
    with pytest.raises(PayloadEnvelopeError, match="authentication failed"):
        decrypt_payload(envelope, **binding, key=KEY)


def test_wrong_key_and_tampering_fail_closed() -> None:
    envelope = encrypt_payload({"private": "value"}, **BINDING, key=KEY)
    with pytest.raises(PayloadEnvelopeError, match="authentication failed"):
        decrypt_payload(envelope, **BINDING, key=b"x" * 32)
    tampered = EncryptedPayload(
        version=envelope.version,
        nonce_b64=envelope.nonce_b64,
        ciphertext_b64=base64.urlsafe_b64encode(b"tampered").decode("ascii"),
    )
    with pytest.raises(PayloadEnvelopeError, match="authentication failed"):
        decrypt_payload(tampered, **BINDING, key=KEY)


def test_unknown_version_and_bad_key_are_rejected() -> None:
    envelope = encrypt_payload({"a": 1}, **BINDING, key=KEY)
    with pytest.raises(PayloadEnvelopeError, match="version"):
        decrypt_payload(
            EncryptedPayload(999, envelope.nonce_b64, envelope.ciphertext_b64),
            **BINDING,
            key=KEY,
        )
    with pytest.raises(PayloadEnvelopeError, match="32 bytes"):
        encrypt_payload({"a": 1}, **BINDING, key=b"short")


def test_missing_or_invalid_environment_key_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MRH_WORKFLOW_PAYLOAD_KEY", raising=False)
    with pytest.raises(PayloadEnvelopeError, match="not configured"):
        load_payload_key()
    with pytest.raises(PayloadEnvelopeError, match="32 bytes"):
        load_payload_key(base64.urlsafe_b64encode(b"short").decode("ascii"))


def test_non_json_and_oversized_payload_are_rejected() -> None:
    with pytest.raises(PayloadEnvelopeError, match="finite JSON"):
        encrypt_payload({"not_finite": float("nan")}, **BINDING, key=KEY)
    with pytest.raises(PayloadEnvelopeError, match="size limit"):
        encrypt_payload({"data": "x" * 1_100_000}, **BINDING, key=KEY)
