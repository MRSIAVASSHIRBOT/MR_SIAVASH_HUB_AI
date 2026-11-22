import hashlib
import json
from uuid import uuid4

import pytest

from mrhub.agents.plan_repository import AgentWorkOrderPlanRepository
from mrhub.domain.tasks import RiskClass, TaskRecord
from mrhub.infrastructure.database import TaskRepository
from mrhub.jobs.payload_envelope import encrypt_payload, encrypt_plan_payload
from mrhub.jobs.recovery import WorkflowRecoveryError, WorkflowRecoveryRepository

KEY = b"p" * 32
OWNER = "awi-plan-owner"


def _database(tmp_path):
    repository = TaskRepository(tmp_path / "awi-plan-consumption.sqlite3")
    repository.initialize()
    with repository._connection() as connection:
        connection.execute(
            """
            INSERT INTO auth_users (
                user_id, username, salt, password_hash, created_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                OWNER,
                "awi-plan-owner@example.test",
                "salt",
                "hash",
                "2026-11-22T20:00:00+00:00",
            ),
        )
    return repository


def _create_plan(repository):
    plan_id = str(uuid4())
    payload = {
        "work_order": {"goal": "Review one safe capability"},
        "plan": {"steps": [{"step_id": "review"}]},
    }
    digest = hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    envelope = encrypt_plan_payload(
        payload,
        plan_id=plan_id,
        owner_user_id=OWNER,
        key=KEY,
    )
    record = AgentWorkOrderPlanRepository(repository.database_path).create(
        plan_id=plan_id,
        owner_user_id=OWNER,
        plan_digest=digest,
        envelope=envelope,
        ttl_seconds=900,
    )
    return record


def _create_workflow(recovery, *, task, workflow_id, plan_record, request_digest):
    workflow_envelope = encrypt_payload(
        {"goal": "safe plan workflow"},
        workflow_id=str(workflow_id),
        task_id=str(task.task_id),
        owner_user_id=OWNER,
        key=KEY,
    )
    return recovery.create_run(
        request_digest,
        [
            {
                "step_number": 1,
                "kind": "provider_selection",
                "name": "provider_selection",
            },
            {
                "step_number": 2,
                "kind": "safe_tool",
                "name": "text.echo",
            },
        ],
        task=task,
        owner_user_id=OWNER,
        payload_envelope=workflow_envelope.model_dump(mode="json"),
        workflow_id=workflow_id,
        idempotency_binding={
            "scope": f"awi-plan-exec:{OWNER}",
            "key": "request-1",
        },
        plan_consumption={
            "plan_id": plan_record.plan_id,
            "owner_user_id": OWNER,
            "plan_digest": plan_record.plan_digest,
        },
    )


def test_plan_consumption_and_workflow_enqueue_are_atomic(tmp_path):
    repository = _database(tmp_path)
    plan_record = _create_plan(repository)
    recovery = WorkflowRecoveryRepository(repository.database_path)
    task = TaskRecord(
        task_type="agent.workflow",
        description="GPI/AWI plan execution",
        risk_class=RiskClass.LOW,
    )
    workflow_id = uuid4()

    created = _create_workflow(
        recovery,
        task=task,
        workflow_id=workflow_id,
        plan_record=plan_record,
        request_digest="a" * 64,
    )

    assert created == workflow_id
    stored_workflow = recovery.get_run(workflow_id, owner_user_id=OWNER)
    assert stored_workflow is not None
    assert stored_workflow["status"] == "queued"

    consumed = AgentWorkOrderPlanRepository(repository.database_path).get(
        plan_record.plan_id,
        owner_user_id=OWNER,
    )
    assert consumed is not None
    assert consumed.status == "consumed"
    assert consumed.workflow_id == str(workflow_id)
    assert consumed.consumed_at is not None
    assert consumed.envelope.nonce_b64 == "consumed"
    assert consumed.envelope.ciphertext_b64 == "consumed"

    with repository._connection() as connection:
        workflow_count = connection.execute(
            "SELECT COUNT(*) FROM workflow_runs WHERE workflow_id = ?",
            (str(workflow_id),),
        ).fetchone()[0]
        task_count = connection.execute(
            "SELECT COUNT(*) FROM tasks WHERE task_id = ?",
            (str(task.task_id),),
        ).fetchone()[0]
        idempotency_count = connection.execute(
            "SELECT COUNT(*) FROM idempotency_records WHERE scope = ? AND idempotency_key = ?",
            (f"awi-plan-exec:{OWNER}", "request-1"),
        ).fetchone()[0]
    assert workflow_count == task_count == idempotency_count == 1


@pytest.mark.parametrize("failure", ["expired", "digest_mismatch"])
def test_failed_plan_consumption_rolls_back_task_workflow_and_idempotency(
    tmp_path,
    failure,
):
    repository = _database(tmp_path)
    plan_record = _create_plan(repository)
    if failure == "expired":
        with repository._connection() as connection:
            connection.execute(
                """
                UPDATE agent_work_order_plans
                SET expires_at = '2000-01-01T00:00:00+00:00'
                WHERE plan_id = ?
                """,
                (plan_record.plan_id,),
            )
    recovery = WorkflowRecoveryRepository(repository.database_path)
    task = TaskRecord(
        task_type="agent.workflow",
        description="GPI/AWI plan execution",
        risk_class=RiskClass.LOW,
    )
    workflow_id = uuid4()
    plan_digest = (
        "f" * 64 if failure == "digest_mismatch" else plan_record.plan_digest
    )

    with pytest.raises(WorkflowRecoveryError, match="Plan is not active"):
        # Exercise the transaction directly with a caller-supplied stale or changed digest.
        wrong_record = plan_record.__class__(
            **{
                **plan_record.__dict__,
                "plan_digest": plan_digest,
            }
        )
        _create_workflow(
            recovery,
            task=task,
            workflow_id=workflow_id,
            plan_record=wrong_record,
            request_digest="b" * 64,
        )

    with repository._connection() as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM workflow_runs WHERE workflow_id = ?",
            (str(workflow_id),),
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM tasks WHERE task_id = ?",
            (str(task.task_id),),
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM idempotency_records WHERE scope = ? AND idempotency_key = ?",
            (f"awi-plan-exec:{OWNER}", "request-1"),
        ).fetchone()[0] == 0
        row = connection.execute(
            "SELECT status, workflow_id, consumed_at FROM agent_work_order_plans WHERE plan_id = ?",
            (plan_record.plan_id,),
        ).fetchone()
    assert row["status"] == "active"
    assert row["workflow_id"] is None
    assert row["consumed_at"] is None
