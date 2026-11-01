from uuid import uuid4

import pytest

from mrhub.jobs.workflow_inputs import WorkflowInputCipher, WorkflowInputError


def test_workflow_input_cipher_round_trips_json_without_plaintext():
    cipher = WorkflowInputCipher(WorkflowInputCipher.generate_key())
    workflow_id = uuid4()
    payload = {"goal": "keep private", "tools": [{"name": "text.echo", "payload": {"text": "secret"}}]}

    ciphertext, digest = cipher.encrypt(workflow_id, "owner-1", payload)

    assert b"keep private" not in ciphertext
    assert b"secret" not in ciphertext
    assert cipher.decrypt(workflow_id, "owner-1", ciphertext, digest) == payload


def test_workflow_input_cipher_binds_ciphertext_to_owner_and_workflow():
    cipher = WorkflowInputCipher(WorkflowInputCipher.generate_key())
    workflow_id = uuid4()
    ciphertext, digest = cipher.encrypt(workflow_id, "owner-1", {"goal": "private"})

    with pytest.raises(WorkflowInputError, match="authentication failed"):
        cipher.decrypt(workflow_id, "owner-2", ciphertext, digest)
    with pytest.raises(WorkflowInputError, match="authentication failed"):
        cipher.decrypt(uuid4(), "owner-1", ciphertext, digest)


def test_workflow_input_cipher_rejects_tampering_and_wrong_digest():
    cipher = WorkflowInputCipher(WorkflowInputCipher.generate_key())
    workflow_id = uuid4()
    ciphertext, digest = cipher.encrypt(workflow_id, "owner-1", {"goal": "private"})

    tampered = ciphertext[:-1] + bytes([ciphertext[-1] ^ 1])
    with pytest.raises(WorkflowInputError, match="authentication failed"):
        cipher.decrypt(workflow_id, "owner-1", tampered, digest)
    with pytest.raises(WorkflowInputError, match="integrity check failed"):
        cipher.decrypt(workflow_id, "owner-1", ciphertext, "0" * 64)


def test_workflow_input_cipher_fails_closed_on_invalid_key():
    with pytest.raises(WorkflowInputError, match="exactly 32 bytes"):
        WorkflowInputCipher("short")
