from datetime import UTC, datetime
import hashlib
import json
from uuid import uuid4

from client_helpers import authenticated_client, run_worker_once
from mrhub.agents.awi_planner import ExecutionPlan, PlanStep
from mrhub.agents.plan_repository import AgentWorkOrderPlanRepository
from mrhub.agents.work_order import WorkOrder
from mrhub.config import get_settings
from mrhub.infrastructure.database import TaskRepository
from mrhub.jobs.payload_envelope import encrypt_plan_payload, load_payload_key


def _digest(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _owner_id() -> str:
    tasks = TaskRepository(get_settings().database_path)
    tasks.initialize()
    with tasks._connection() as connection:
        row = connection.execute("SELECT user_id FROM auth_users LIMIT 1").fetchone()
    assert row is not None
    return str(row["user_id"])


def _persist_plan(criterion: str) -> tuple[str, dict[str, object], str]:
    owner_id = _owner_id()
    work_order = WorkOrder.model_validate(
        {
            "goal": "Verify one explicit durable workflow step",
            "intent": "Check a deterministic execution criterion",
            "scope": "Read-only evidence evaluation",
            "required_capabilities": ["text.echo"],
            "acceptance_criteria": [criterion],
            "verification_steps": ["Inspect the owner-scoped workflow step record"],
            "risk_class": "low",
        }
    )
    plan = ExecutionPlan(
        steps=[
            PlanStep(
                step_id="step-2",
                description="Verify the explicitly named workflow step",
                depends_on=[],
                required_capabilities=["text.echo"],
                verifies_criteria=[criterion],
                verification="Check the persisted workflow step state and digest",
            )
        ],
        rationale="A single declarative step covers this criterion.",
    )
    payload = {
        "work_order": work_order.model_dump(mode="json"),
        "plan": plan.model_dump(mode="json"),
    }
    plan_id = str(uuid4())
    envelope = encrypt_plan_payload(
        payload,
        plan_id=plan_id,
        owner_user_id=owner_id,
        key=load_payload_key(),
    )
    AgentWorkOrderPlanRepository(get_settings().database_path).create(
        plan_id=plan_id,
        owner_user_id=owner_id,
        plan_digest=_digest(payload),
        envelope=envelope,
        ttl_seconds=900,
    )
    return plan_id, work_order.model_dump(mode="json"), _digest(
        work_order.model_dump(mode="json")
    )


def _run_verified_echo(client):
    submitted = client.post(
        "/agent/workflows",
        json={
            "goal": "Run a deterministic evidence-producing step",
            "tools": [{"name": "text.echo", "payload": {"text": "evidence marker"}}],
        },
    )
    assert submitted.status_code == 200
    workflow_id = submitted.json()["workflow"]["workflow_id"]
    assert run_worker_once() is not None
    history = client.get(f"/agent/workflows/{workflow_id}")
    assert history.status_code == 200
    workflow = history.json()
    step = next(row for row in workflow["steps"] if row["step_key"] == "step-2")
    assert step["status"] == "succeeded"
    assert isinstance(step["output_digest"], str)
    return workflow_id, step


def _evidence(work_order_digest: str, workflow_id: str, step: dict[str, object]):
    return {
        "evidence_id": "evidence_step_001",
        "criterion_id": "ac_001",
        "source_type": "agent_workflow_step",
        "source_ref": f"{workflow_id}/{step['step_key']}",
        "evidence_digest": step["output_digest"],
        "work_order_digest": work_order_digest,
        "work_order_revision": 1,
        "observed_at": datetime.now(UTC).isoformat(),
        "verifier_id": "hub.workflow_step.v1",
    }


def test_registered_workflow_step_evidence_accepts_only_exact_typed_criterion():
    client = authenticated_client()
    criterion = "workflow_step_succeeded:step-2"
    plan_id, _work_order, work_order_digest = _persist_plan(criterion)
    workflow_id, step = _run_verified_echo(client)

    response = client.post(
        f"/agent/work-orders/plans/{plan_id}/evidence/evaluate",
        json={"evidence": [_evidence(work_order_digest, workflow_id, step)]},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["report"]["decision"] == "accept"
    assert body["report"]["criteria"][0]["status"] == "passed"
    assert body["report"]["read_only"] is True
    assert body["report"]["execution_started"] is False
    assert body["report"]["permissions_changed"] is False
    assert body["execution_started"] is False
    assert body["permissions_changed"] is False
    assert body["correction_proposal"]["items"] == []
    assert body["correction_proposal"]["evidence_report_digest"] == body["report"]["report_digest"]
    assert body["correction_proposal"]["execution_started"] is False
    assert body["correction_proposal"]["automatic_retry"] is False
    assert body["verifier_contract"] == "hub.workflow_step.v1"
    assert body["decision_scope"] == "declared_work_order_acceptance_criteria_only"
    assert body["goal_completion_claimed"] is False
    assert body["human_review_required_for_goal_completion"] is True
    assert client.get(f"/agent/workflows/{workflow_id}").json()["status"] == "succeeded"


def test_non_typed_goal_criterion_remains_unknown_even_with_successful_step():
    client = authenticated_client()
    plan_id, _work_order, work_order_digest = _persist_plan(
        "The complete product goal has been achieved"
    )
    workflow_id, step = _run_verified_echo(client)

    response = client.post(
        f"/agent/work-orders/plans/{plan_id}/evidence/evaluate",
        json={"evidence": [_evidence(work_order_digest, workflow_id, step)]},
    )

    assert response.status_code == 200
    report = response.json()["report"]
    assert report["decision"] == "review_required"
    assert report["criteria"][0]["status"] == "unknown"
    assert "unsupported_criterion_verification" in report["criteria"][0]["reason_codes"]


def test_foreign_or_unknown_workflow_evidence_cannot_pass():
    client = authenticated_client()
    criterion = "workflow_step_succeeded:step-2"
    plan_id, _work_order, work_order_digest = _persist_plan(criterion)
    unknown_workflow = str(uuid4())
    evidence = {
        "evidence_id": "evidence_step_002",
        "criterion_id": "ac_001",
        "source_type": "agent_workflow_step",
        "source_ref": f"{unknown_workflow}/step-2",
        "evidence_digest": "a" * 64,
        "work_order_digest": work_order_digest,
        "work_order_revision": 1,
        "observed_at": datetime.now(UTC).isoformat(),
        "verifier_id": "hub.workflow_step.v1",
    }

    response = client.post(
        f"/agent/work-orders/plans/{plan_id}/evidence/evaluate",
        json={"evidence": [evidence]},
    )

    assert response.status_code == 200
    report = response.json()["report"]
    assert report["decision"] == "review_required"
    assert report["criteria"][0]["status"] == "unknown"
    assert "workflow_not_found_or_not_owned" in report["criteria"][0]["reason_codes"]


def test_stale_work_order_digest_is_never_accepted():
    client = authenticated_client()
    criterion = "workflow_step_succeeded:step-2"
    plan_id, _work_order, work_order_digest = _persist_plan(criterion)
    workflow_id, step = _run_verified_echo(client)
    evidence = _evidence(work_order_digest, workflow_id, step)
    evidence["work_order_digest"] = "f" * 64

    response = client.post(
        f"/agent/work-orders/plans/{plan_id}/evidence/evaluate",
        json={"evidence": [evidence]},
    )

    assert response.status_code == 200
    report = response.json()["report"]
    assert report["decision"] == "review_required"
    assert report["criteria"][0]["status"] == "stale"
    assert "stale_work_order_reference" in report["criteria"][0]["reason_codes"]


def test_plan_evidence_api_is_owner_scoped_and_no_store():
    client = authenticated_client()
    plan_id, _work_order, _digest_value = _persist_plan(
        "workflow_step_succeeded:step-2"
    )

    response = client.post(
        f"/agent/work-orders/plans/{plan_id}/evidence/evaluate",
        json={"evidence": []},
    )
    assert response.status_code == 200
    assert response.headers["cache-control"] == "private, no-store"
    assert response.json()["report"]["decision"] == "review_required"

    missing = client.post(
        "/agent/work-orders/plans/00000000-0000-4000-8000-000000000001/evidence/evaluate",
        json={"evidence": []},
    )
    assert missing.status_code == 404


def test_workflow_evidence_rejects_same_step_id_with_different_tool_capability():
    from mrhub.agents.work_order_evidence import (
        EvidenceReference,
        WorkOrderCriterion,
        VerifierStatus,
    )
    from mrhub.api.routes.agent_evidence import _workflow_step_verifier

    workflow_id = "123e4567-e89b-12d3-a456-426614174000"

    class FakeWorkflowRepository:
        def get_run(self, workflow_id_value, *, owner_user_id):
            assert str(workflow_id_value) == workflow_id
            assert owner_user_id == "owner-a"
            return {
                "steps": [
                    {
                        "step_key": "step-2",
                        "step_name": "different.tool",
                        "status": "succeeded",
                        "output_digest": "a" * 64,
                    }
                ]
            }

    reference = EvidenceReference(
        evidence_id="evidence_mismatch",
        criterion_id="ac_001",
        source_type="agent_workflow_step",
        source_ref=f"{workflow_id}/step-2",
        evidence_digest="a" * 64,
        work_order_digest="b" * 64,
        work_order_revision=1,
        observed_at=datetime.now(UTC).isoformat(),
        verifier_id="hub.workflow_step.v1",
    )
    criterion = WorkOrderCriterion(
        criterion_id="ac_001",
        description="workflow_step_succeeded:step-2",
    )

    result = _workflow_step_verifier(
        reference,
        criterion,
        repository=FakeWorkflowRepository(),
        owner_user_id="owner-a",
        planned_step_capabilities={"step-2": frozenset({"text.echo"})},
    )

    assert result.status is VerifierStatus.UNKNOWN
    assert result.reason_code == "workflow_step_capability_mismatch"
