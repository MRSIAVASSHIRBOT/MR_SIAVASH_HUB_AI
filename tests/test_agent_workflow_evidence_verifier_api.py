from datetime import UTC, datetime
from uuid import uuid4

from client_helpers import authenticated_client, run_worker_once
from mrhub.agents.awi_planner import ExecutionPlan, PlanStep
from mrhub.agents.plan_repository import AgentWorkOrderPlanRepository
from mrhub.agents.work_order import WorkOrder
from mrhub.api.dependencies import get_auth_service
from mrhub.api.routes.agent import _canonical_plan_digest
from mrhub.config import get_settings
from mrhub.domain.tasks import RiskClass
from mrhub.jobs.payload_envelope import encrypt_plan_payload, load_payload_key


def _create_plan(client, criterion: str, capability: str) -> tuple[str, str]:
    token = client.headers["Authorization"].split(" ", maxsplit=1)[1]
    owner = get_auth_service().authenticate(token)
    assert owner is not None

    work_order = WorkOrder(
        goal="Verify one exact workflow step",
        intent="check one registered deterministic capability",
        scope="owner-scoped workflow evidence",
        required_capabilities=[capability],
        acceptance_criteria=[criterion],
        verification_steps=["Inspect the exact workflow step and output digest"],
        risk_class=RiskClass.LOW,
    )
    plan = ExecutionPlan(
        steps=[
            PlanStep(
                step_id="step-2",
                description="Execute the capability declared in the plan",
                depends_on=[],
                required_capabilities=[capability],
                verifies_criteria=[criterion],
                verification="Read the persisted step result and digest",
            )
        ],
        rationale="One bounded step covers the criterion.",
    )
    payload = {
        "work_order": work_order.model_dump(mode="json"),
        "plan": plan.model_dump(mode="json"),
    }
    plan_id = str(uuid4())
    envelope = encrypt_plan_payload(
        payload,
        plan_id=plan_id,
        owner_user_id=owner.user_id,
        key=load_payload_key(),
    )
    AgentWorkOrderPlanRepository(get_settings().database_path).create(
        plan_id=plan_id,
        owner_user_id=owner.user_id,
        plan_digest=_canonical_plan_digest(payload),
        envelope=envelope,
        ttl_seconds=900,
    )
    work_order_digest = _canonical_plan_digest(
        {"work_order": work_order.model_dump(mode="json")}
    )
    return plan_id, work_order_digest


def _execute_text_echo_workflow(
    client,
    *,
    work_order_plan_id: str | None = None,
) -> tuple[str, dict[str, object]]:
    request_body = {
        "goal": "Verify one exact workflow step",
        "tools": [
            {
                "step_id": "step-2",
                "depends_on": [],
                "name": "text.echo",
                "payload": {"text": "workflow evidence marker"},
            }
        ],
    }
    if work_order_plan_id is not None:
        request_body["work_order_plan_id"] = work_order_plan_id
    submitted = client.post("/agent/workflows", json=request_body)
    assert submitted.status_code == 200
    workflow_id = submitted.json()["workflow"]["workflow_id"]
    assert run_worker_once() is not None
    workflow_response = client.get(f"/agent/workflows/{workflow_id}")
    assert workflow_response.status_code == 200
    workflow = workflow_response.json()
    step = next(
        item for item in workflow["steps"]
        if item["step_key"] == "step-2"
    )
    assert step["status"] == "succeeded"
    return workflow_id, step


def _evidence(work_order_digest: str, workflow_id: str, step: dict[str, object]):
    return {
        "evidence_id": "workflow_evidence_001",
        "criterion_id": "ac_001",
        "source_type": "agent_workflow_step",
        "source_ref": f"{workflow_id}/{step['step_key']}",
        "evidence_digest": step["output_digest"],
        "work_order_digest": work_order_digest,
        "work_order_revision": 1,
        "observed_at": datetime.now(UTC).isoformat(),
        "verifier_id": "hub.workflow_step.v1",
    }


def test_default_verifier_accepts_only_exact_owner_plan_step_and_capability():
    client = authenticated_client()
    criterion = "workflow_step_succeeded:step-2"
    plan_id, work_order_digest = _create_plan(client, criterion, "text.echo")
    workflow_id, step = _execute_text_echo_workflow(client, work_order_plan_id=plan_id)
    token = client.headers["Authorization"].split(" ", maxsplit=1)[1]
    owner = get_auth_service().authenticate(token)
    assert owner is not None
    persisted_plan = AgentWorkOrderPlanRepository(get_settings().database_path).get(
        plan_id,
        owner_user_id=owner.user_id,
    )
    assert persisted_plan is not None
    assert persisted_plan.status == "consumed"
    assert persisted_plan.workflow_id == workflow_id

    response = client.post(
        f"/agent/work-orders/plans/{plan_id}/evidence/evaluate",
        json={"evidence": [_evidence(work_order_digest, workflow_id, step)]},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["report"]["decision"] == "accept"
    assert body["report"]["criteria"][0]["status"] == "passed"
    assert body["correction_proposal"]["items"] == []
    assert body["correction_proposal"]["evidence_report_digest"] == body["report"]["report_digest"]
    assert body["correction_proposal"]["execution_started"] is False
    assert body["read_only"] is True
    assert body["execution_started"] is False
    assert body["permissions_changed"] is False


def test_default_verifier_keeps_semantic_goal_criteria_unknown():
    client = authenticated_client()
    criterion = "The entire product goal is complete"
    plan_id, work_order_digest = _create_plan(client, criterion, "text.echo")
    workflow_id, step = _execute_text_echo_workflow(client, work_order_plan_id=plan_id)

    response = client.post(
        f"/agent/work-orders/plans/{plan_id}/evidence/evaluate",
        json={"evidence": [_evidence(work_order_digest, workflow_id, step)]},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["report"]["decision"] == "review_required"
    assert body["report"]["criteria"][0]["status"] == "unknown"
    assert "unsupported_criterion_verification" in body["report"]["criteria"][0]["reason_codes"]
    assert body["correction_proposal"]["requires_owner_review"] is True
    assert body["correction_proposal"]["items"][0]["action"] == "gather_or_reconcile_evidence"


def test_default_verifier_rejects_an_unbound_workflow_even_for_the_same_owner_step_and_capability():
    client = authenticated_client()
    criterion = "workflow_step_succeeded:step-2"
    plan_id, work_order_digest = _create_plan(client, criterion, "text.echo")
    # A matching step is not evidence for this plan until the workflow is atomically bound.
    workflow_id, step = _execute_text_echo_workflow(client)

    response = client.post(
        f"/agent/work-orders/plans/{plan_id}/evidence/evaluate",
        json={"evidence": [_evidence(work_order_digest, workflow_id, step)]},
    )

    assert response.status_code == 200
    report = response.json()["report"]
    assert report["decision"] == "review_required"
    assert report["criteria"][0]["status"] == "unknown"
    assert "workflow_not_bound_to_work_order_plan" in report["criteria"][0]["reason_codes"]



def test_plan_binding_rejects_workflow_steps_outside_the_persisted_awiplan():
    client = authenticated_client()
    criterion = "workflow_step_succeeded:step-2"
    plan_id, _work_order_digest = _create_plan(client, criterion, "text.echo")

    response = client.post(
        "/agent/workflows",
        json={
            "goal": "Verify one exact workflow step",
            "work_order_plan_id": plan_id,
            "tools": [
                {
                    "step_id": "different-step",
                    "depends_on": [],
                    "name": "text.echo",
                    "payload": {"text": "workflow evidence marker"},
                }
            ],
        },
    )

    assert response.status_code == 409
    token = client.headers["Authorization"].split(" ", maxsplit=1)[1]
    owner = get_auth_service().authenticate(token)
    assert owner is not None
    record = AgentWorkOrderPlanRepository(get_settings().database_path).get(
        plan_id,
        owner_user_id=owner.user_id,
    )
    assert record is not None
    assert record.status == "active"
    assert record.workflow_id is None
