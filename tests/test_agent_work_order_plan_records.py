from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from mrhub.agents.plan_repository import (
    AgentWorkOrderPlanError,
    AgentWorkOrderPlanRepository,
)
from mrhub.infrastructure.database import TaskRepository
from mrhub.jobs.payload_envelope import (
    EncryptedPayload,
    PayloadEnvelopeError,
    decrypt_payload,
    decrypt_plan_payload,
    encrypt_payload,
    encrypt_plan_payload,
)

KEY = b"p" * 32


class MutableClock:
    def __init__(self):
        self.current = datetime(2026, 11, 22, 20, 0, tzinfo=UTC)

    def __call__(self):
        return self.current


def create_owner(repository: TaskRepository, owner_user_id: str = "owner-plan-1"):
    repository.initialize()
    with repository._connection() as connection:
        connection.execute(
            """
            INSERT INTO auth_users (
                user_id, username, salt, password_hash, created_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                owner_user_id,
                f"{owner_user_id}@example.test",
                "salt",
                "hash",
                "2026-11-22T20:00:00+00:00",
            ),
        )
    return owner_user_id


def encrypted_plan(plan_id: str, owner_user_id: str):
    payload = {
        "work_order": {"goal": "private plan goal", "intent": "review"},
        "plan": {"steps": [{"step_id": "review"}]},
    }
    envelope = encrypt_plan_payload(
        payload,
        plan_id=plan_id,
        owner_user_id=owner_user_id,
        key=KEY,
    )
    return payload, envelope


def test_plan_payload_round_trip_and_resource_binding():
    plan_id = str(uuid4())
    owner = "owner-plan-1"
    payload, envelope = encrypted_plan(plan_id, owner)

    assert decrypt_plan_payload(
        envelope,
        plan_id=plan_id,
        owner_user_id=owner,
        key=KEY,
    ) == payload

    with pytest.raises(PayloadEnvelopeError, match="authentication failed"):
        decrypt_plan_payload(
            envelope,
            plan_id=str(uuid4()),
            owner_user_id=owner,
            key=KEY,
        )
    with pytest.raises(PayloadEnvelopeError, match="authentication failed"):
        decrypt_plan_payload(
            envelope,
            plan_id=plan_id,
            owner_user_id="other-owner",
            key=KEY,
        )


def test_workflow_ciphertext_cannot_be_reused_as_an_agent_plan_envelope():
    workflow_envelope = encrypt_payload(
        {"goal": "not a plan record"},
        workflow_id="workflow-1",
        task_id="task-1",
        owner_user_id="owner-plan-1",
        key=KEY,
    )

    with pytest.raises(PayloadEnvelopeError, match="authentication failed"):
        decrypt_plan_payload(
            workflow_envelope,
            plan_id=str(uuid4()),
            owner_user_id="owner-plan-1",
            key=KEY,
        )


def test_plan_record_is_owner_scoped_and_stores_only_ciphertext(tmp_path):
    database = TaskRepository(tmp_path / "plans.sqlite3")
    owner = create_owner(database)
    clock = MutableClock()
    plans = AgentWorkOrderPlanRepository(database.database_path, clock=clock)
    plan_id = str(uuid4())
    payload, envelope = encrypted_plan(plan_id, owner)

    record = plans.create(
        plan_id=plan_id,
        owner_user_id=owner,
        plan_digest="a" * 64,
        envelope=envelope,
        expires_at=clock.current + timedelta(minutes=15),
    )

    assert record.status == "active"
    assert record.plan_id == plan_id
    assert plans.get(plan_id, owner_user_id="another-owner") is None

    loaded = plans.get(plan_id, owner_user_id=owner)
    assert loaded is not None
    assert loaded.envelope == envelope
    assert decrypt_plan_payload(
        loaded.envelope,
        plan_id=loaded.plan_id,
        owner_user_id=loaded.owner_user_id,
        key=KEY,
    ) == payload

    with database._connection() as connection:
        stored = connection.execute(
            "SELECT * FROM agent_work_order_plans WHERE plan_id = ?",
            (plan_id,),
        ).fetchone()
    assert "private plan goal" not in str(dict(stored))
    assert stored["ciphertext_b64"] == envelope.ciphertext_b64


def test_expired_plan_is_marked_and_never_returned_as_active(tmp_path):
    database = TaskRepository(tmp_path / "expired-plans.sqlite3")
    owner = create_owner(database)
    clock = MutableClock()
    plans = AgentWorkOrderPlanRepository(database.database_path, clock=clock)
    plan_id = str(uuid4())
    _payload, envelope = encrypted_plan(plan_id, owner)

    plans.create(
        plan_id=plan_id,
        owner_user_id=owner,
        plan_digest="b" * 64,
        envelope=envelope,
        expires_at=clock.current + timedelta(seconds=60),
    )
    clock.current += timedelta(seconds=61)

    loaded = plans.get(plan_id, owner_user_id=owner)
    assert loaded is not None
    assert loaded.status == "expired"
    assert plans.get(plan_id, owner_user_id=owner).status == "expired"


@pytest.mark.parametrize(
    ("plan_id", "owner", "digest", "ttl"),
    [
        ("not-a-uuid", "owner-plan-1", "c" * 64, 900),
        (str(uuid4()), "", "c" * 64, 900),
        (str(uuid4()), "owner-plan-1", "not-a-digest", 900),
        (str(uuid4()), "owner-plan-1", "c" * 64, 30),
        (str(uuid4()), "owner-plan-1", "c" * 64, 86_401),
    ],
)
def test_invalid_plan_record_inputs_are_rejected(tmp_path, plan_id, owner, digest, ttl):
    database = TaskRepository(tmp_path / "invalid-plans.sqlite3")
    valid_owner = create_owner(database)
    clock = MutableClock()
    plans = AgentWorkOrderPlanRepository(database.database_path, clock=clock)
    actual_owner = valid_owner if owner == "owner-plan-1" else owner
    _payload, envelope = encrypted_plan(str(uuid4()), valid_owner)

    with pytest.raises(AgentWorkOrderPlanError):
        plans.create(
            plan_id=plan_id,
            owner_user_id=actual_owner,
            plan_digest=digest,
            envelope=envelope,
            expires_at=clock.current + timedelta(seconds=ttl),
        )


def test_plan_record_rejects_unknown_or_noncanonical_plan_identifiers(tmp_path):
    database = TaskRepository(tmp_path / "missing-plan.sqlite3")
    create_owner(database)
    plans = AgentWorkOrderPlanRepository(database.database_path)

    assert plans.get("missing", owner_user_id="owner-plan-1") is None
    assert plans.get(str(uuid4()).upper(), owner_user_id="owner-plan-1") is None


def test_plan_payload_rejects_non_json_and_oversized_values():
    plan_id = str(uuid4())
    with pytest.raises(PayloadEnvelopeError, match="finite JSON"):
        encrypt_plan_payload(
            {"value": float("nan")},
            plan_id=plan_id,
            owner_user_id="owner-plan-1",
            key=KEY,
        )
    with pytest.raises(PayloadEnvelopeError, match="size limit"):
        encrypt_plan_payload(
            {"value": "x" * 1_100_000},
            plan_id=plan_id,
            owner_user_id="owner-plan-1",
            key=KEY,
        )


def test_plan_envelope_rejects_tampered_ciphertext():
    plan_id = str(uuid4())
    _payload, envelope = encrypted_plan(plan_id, "owner-plan-1")
    tampered = EncryptedPayload(
        version=envelope.version,
        nonce_b64=envelope.nonce_b64,
        ciphertext_b64="dGFtcGVyZWQ=",
    )

    with pytest.raises(PayloadEnvelopeError, match="authentication failed"):
        decrypt_plan_payload(
            tampered,
            plan_id=plan_id,
            owner_user_id="owner-plan-1",
            key=KEY,
        )
