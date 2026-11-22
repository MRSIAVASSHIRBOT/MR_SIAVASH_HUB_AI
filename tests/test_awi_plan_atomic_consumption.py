import hashlib
import json
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

import pytest

from mrhub.agents.awi_planner import ExecutionPlan, PlanStep
from mrhub.agents.plan_repository import AgentWorkOrderPlanRepository
from mrhub.agents.work_order import WorkOrder
from mrhub.api.routes import agent as agent_routes
from mrhub.domain.tasks import RiskClass, TaskRecord
from mrhub.infrastructure.database import TaskRepository
from mrhub.jobs.payload_envelope import (
    encrypt_payload,
    encrypt_plan_payload,
    load_payload_key,
)
from mrhub.providers.base import ProviderHealth, ProviderResponse
from mrhub.providers.router import ModelCapability, ModelDescriptor, ModelRouter
from mrhub.tools.registry import ToolDefinition, ToolRegistry
from client_helpers import authenticated_client, run_worker_once
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


class _SelectionOnlyProvider:
    """A deterministic, local provider used only for model selection in tests."""

    def __init__(self):
        self.descriptor = ModelDescriptor(
            provider="awi-test",
            model="selection-only",
            capability=ModelCapability(text=True),
            available=True,
            local=True,
            priority=1,
        )

    def generate(self, request):
        return ProviderResponse(
            provider=self.descriptor.provider,
            model=self.descriptor.model,
            output_text="{}",
        )

    def health(self, timeout_seconds: float = 2.0):
        return ProviderHealth(available=True, reason_code="test_ready")


def _selection_router():
    router = ModelRouter()
    router.register_provider(_SelectionOnlyProvider())
    return router


def _persist_echo_plan(client, *, goal="Echo one short text value"):
    from mrhub.domain.tasks import RiskClass

    repository = TaskRepository(get_settings().database_path)
    repository.initialize()
    with repository._connection() as connection:
        owner = connection.execute(
            "SELECT user_id FROM auth_users WHERE username = 'owner'"
        ).fetchone()["user_id"]

    plan_id = str(uuid4())
    criterion = "The supplied text is returned unchanged"
    work_order = WorkOrder(
        goal=goal,
        intent="Return one supplied text value unchanged",
        scope="Use only the registered text.echo demonstration tool",
        assumptions=["The supplied text is non-sensitive"],
        constraints=["No external side effects"],
        dependencies=[],
        required_capabilities=["text.echo"],
        acceptance_criteria=[criterion],
        verification_steps=["Compare the returned text with the supplied input"],
        risk_class=RiskClass.LOW,
    )
    plan = ExecutionPlan(
        rationale="One bounded demonstration step",
        steps=[
            PlanStep(
                step_id="echo_text",
                description="Echo the supplied short text",
                depends_on=[],
                required_capabilities=["text.echo"],
                verifies_criteria=[criterion],
                verification="Confirm the returned value matches the input",
            )
        ],
    )
    payload = {
        "work_order": work_order.model_dump(mode="json"),
        "plan": plan.model_dump(mode="json"),
    }
    digest = agent_routes._canonical_plan_digest(payload)
    envelope = encrypt_plan_payload(
        payload,
        plan_id=plan_id,
        owner_user_id=owner,
        key=load_payload_key(),
    )
    AgentWorkOrderPlanRepository(repository.database_path).create(
        plan_id=plan_id,
        owner_user_id=owner,
        plan_digest=digest,
        envelope=envelope,
        ttl_seconds=900,
    )
    return repository, owner, plan_id, digest


def _execute_echo(client, plan_id, digest, *, text="safe-value", key="awi-exec-1"):
    return client.post(
        f"/agent/work-orders/plans/{plan_id}/execute",
        headers={"Idempotency-Key": key},
        json={
            "plan_digest": digest,
            "bindings": [{
                "step_id": "echo_text",
                "tool_name": "text.echo",
                "payload": {"text": text},
            }],
        },
    )


def test_persisted_plan_execution_is_queued_idempotent_and_worker_owned(monkeypatch):
    client = authenticated_client()
    router = _selection_router()
    monkeypatch.setattr(agent_routes, "build_model_router", lambda: router)

    repository, owner, plan_id, digest = _persist_echo_plan(client)
    created = _execute_echo(client, plan_id, digest)
    assert created.status_code == 200
    body = created.json()
    workflow_id = body["workflow"]["workflow_id"]
    assert body["queued"] is True
    assert body["idempotent_replay"] is False
    assert body["plan_consumed"] is True
    assert body["execution_started"] is False
    assert body["tools_executed"] is False
    assert body["permissions_changed"] is False
    assert created.headers["cache-control"] == "private, no-store"

    consumed = AgentWorkOrderPlanRepository(repository.database_path).get(
        plan_id,
        owner_user_id=owner,
    )
    assert consumed is not None
    assert consumed.status == "consumed"
    assert consumed.workflow_id == workflow_id

    replay = _execute_echo(client, plan_id, digest)
    assert replay.status_code == 200
    assert replay.json()["idempotent_replay"] is True
    assert replay.json()["workflow"]["workflow_id"] == workflow_id

    changed_replay = _execute_echo(client, plan_id, digest, text="different", key="awi-exec-1")
    assert changed_replay.status_code == 409

    with repository._connection() as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM workflow_runs WHERE workflow_id = ?",
            (workflow_id,),
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM tasks WHERE task_type = 'agent.workflow' AND description = 'GPI/AWI plan execution'"
        ).fetchone()[0] == 1

    import mrhub.jobs.workflow_dispatch as workflow_dispatch

    monkeypatch.setattr(workflow_dispatch, "build_model_router", lambda: router)
    completed = run_worker_once()
    assert completed is not None
    assert completed.status.value == "succeeded"

    final = client.get(f"/agent/workflows/{workflow_id}")
    assert final.status_code == 200
    assert final.json()["status"] == "succeeded"
    with repository._connection() as connection:
        task_status = connection.execute(
            "SELECT status FROM tasks WHERE task_id = ?",
            (final.json()["task_id"],),
        ).fetchone()["status"]
    assert task_status == "succeeded"


def test_worker_fails_closed_when_registered_tool_schema_changes(monkeypatch):
    client = authenticated_client()
    router = _selection_router()
    monkeypatch.setattr(agent_routes, "build_model_router", lambda: router)

    repository, owner, plan_id, digest = _persist_echo_plan(client)
    created = _execute_echo(client, plan_id, digest, key="awi-schema-change")
    assert created.status_code == 200
    workflow_id = created.json()["workflow"]["workflow_id"]

    invoked = []

    class ChangedEchoInput(BaseModel):
        model_config = ConfigDict(extra="forbid")

        text: str = Field(min_length=1, max_length=100)

    class EchoOutput(BaseModel):
        text: str
        character_count: int = Field(ge=1, le=500)

    changed_registry = ToolRegistry()
    changed_registry.register(
        ToolDefinition(
            name="text.echo",
            description="Changed contract for testing",
            input_model=ChangedEchoInput,
            output_model=EchoOutput,
            handler=lambda value: invoked.append(value.text) or {
                "text": value.text,
                "character_count": len(value.text),
            },
            risk_class=RiskClass.LOW,
            external_side_effect=False,
        )
    )

    import mrhub.jobs.workflow_dispatch as workflow_dispatch

    monkeypatch.setattr(workflow_dispatch, "build_model_router", lambda: router)
    monkeypatch.setattr(
        workflow_dispatch,
        "build_tool_registry",
        lambda **_kwargs: changed_registry,
    )

    completed = run_worker_once()
    assert completed is not None
    assert completed.status.value == "failed"
    assert invoked == []

    final = client.get(f"/agent/workflows/{workflow_id}")
    assert final.status_code == 200
    assert final.json()["status"] == "failed"

    consumed = AgentWorkOrderPlanRepository(repository.database_path).get(
        plan_id,
        owner_user_id=owner,
    )
    assert consumed is not None and consumed.status == "consumed"


def test_high_risk_goal_cannot_consume_plan_or_enqueue_workflow(monkeypatch):
    client = authenticated_client()
    router = _selection_router()
    monkeypatch.setattr(agent_routes, "build_model_router", lambda: router)

    repository, owner, plan_id, digest = _persist_echo_plan(
        client,
        goal="Delete a production database and echo a value",
    )
    result = _execute_echo(client, plan_id, digest, key="awi-high-risk")
    assert result.status_code == 403

    stored = AgentWorkOrderPlanRepository(repository.database_path).get(
        plan_id,
        owner_user_id=owner,
    )
    assert stored is not None
    assert stored.status == "active"
    with repository._connection() as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM workflow_runs"
        ).fetchone()[0] == 0
