from __future__ import annotations

from uuid import uuid4

from client_helpers import authenticated_client
from mrhub.agents.awi_planner import ExecutionPlan, PlanStep
from mrhub.agents.plan_repository import AgentWorkOrderPlanRepository
from mrhub.agents.work_order import WorkOrder
from mrhub.agents.work_order_evidence import (
    EvidenceReference,
    EvidenceVerification,
    EvidenceVerifierRegistry,
    VerifierStatus,
)
from mrhub.api.dependencies import get_auth_service
from mrhub.api.routes.agent import _canonical_plan_digest
from mrhub.config import get_settings
from mrhub.domain.tasks import RiskClass
from mrhub.infrastructure.database import TaskRepository
from mrhub.jobs.payload_envelope import encrypt_plan_payload, load_payload_key


def _create_owned_plan(client) -> tuple[str, str]:
    """Persist a minimal encrypted plan for the owner authenticated by this client."""
    authorization = client.headers["Authorization"]
    token = authorization.split(" ", maxsplit=1)[1]
    owner = get_auth_service().authenticate(token)
    assert owner is not None

    settings = get_settings()
    tasks = TaskRepository(settings.database_path)
    tasks.initialize()
    plan_id = str(uuid4())
    work_order = WorkOrder(
        goal="Review one local build result",
        intent="verify a bounded local build",
        scope="one non-production repository check",
        acceptance_criteria=["The expected local build check is successful"],
        verification_steps=["Read the exact check-run conclusion"],
        risk_class=RiskClass.LOW,
    )
    plan = ExecutionPlan(
        steps=[
            PlanStep(
                step_id="review-build",
                description="Read one exact build result",
                verifies_criteria=["The expected local build check is successful"],
                verification="Confirm the trusted check-run result",
            )
        ],
        rationale="A single deterministic read-only verification step",
    )
    payload = {
        "work_order": work_order.model_dump(mode="json"),
        "plan": plan.model_dump(mode="json"),
    }
    digest = _canonical_plan_digest(payload)
    envelope = encrypt_plan_payload(
        payload,
        plan_id=plan_id,
        owner_user_id=owner.user_id,
        key=load_payload_key(),
    )
    AgentWorkOrderPlanRepository(settings.database_path).create(
        plan_id=plan_id,
        owner_user_id=owner.user_id,
        plan_digest=digest,
        envelope=envelope,
        ttl_seconds=900,
    )
    return plan_id, digest


def _reference(plan_digest: str) -> dict[str, object]:
    return {
        "evidence_id": "evidence-001",
        "criterion_id": "ac_001",
        "source_type": "test.fixture",
        "source_ref": "test-runs/123/checks/1",
        "evidence_digest": "b" * 64,
        "work_order_digest": plan_digest,
        "work_order_revision": 1,
        "observed_at": "2026-11-27T00:00:00+00:00",
        "verifier_id": "test.fixture.passed",
    }


def test_work_order_evidence_api_is_owner_authenticated():
    from fastapi.testclient import TestClient
    from mrhub.main import create_app

    response = TestClient(create_app()).post(
        "/agent/work-orders/plans/00000000-0000-0000-0000-000000000001/evidence/evaluate",
        json={"evidence": []},
    )

    assert response.status_code in (401, 403)


def test_work_order_evidence_api_returns_review_required_without_trusted_verifier():
    client = authenticated_client()
    plan_id, plan_digest = _create_owned_plan(client)

    response = client.post(
        f"/agent/work-orders/plans/{plan_id}/evidence/evaluate",
        json={"evidence": [_reference(plan_digest)]},
    )

    assert response.status_code == 200
    body = response.json()
    report = body["report"]
    assert report["decision"] == "review_required"
    assert report["criteria"][0]["status"] == "unknown"
    assert "unregistered_verifier" in report["criteria"][0]["reason_codes"]
    assert body["plan_digest"] == plan_digest
    assert body["criteria_map"] == {
        "ac_001": "The expected local build check is successful"
    }
    assert body["read_only"] is True
    assert body["execution_started"] is False
    assert body["tools_executed"] is False
    assert body["permissions_changed"] is False

    audit = TaskRepository(get_settings().database_path).list_audit()
    event = next(
        item for item in audit
        if item["event_type"] == "agent.work_order_evidence_evaluated"
    )
    assert event["subject_id"] == plan_id
    assert event["metadata"]["decision"] == "review_required"
    assert event["metadata"]["evidence_count"] == 1
    assert event["metadata"]["criterion_count"] == 1
    assert event["metadata"]["report_digest"] == report["report_digest"]
    assert "test-runs/123/checks/1" not in str(event)


def test_work_order_evidence_api_accepts_only_server_registered_verifier():
    client = authenticated_client()
    plan_id, plan_digest = _create_owned_plan(client)
    registry = EvidenceVerifierRegistry()
    registry.register(
        source_type="test.fixture",
        verifier_id="test.fixture.passed",
        verifier=lambda reference, criterion: EvidenceVerification(
            status=VerifierStatus.PASSED,
            evidence_digest=reference.evidence_digest,
            reason_code="trusted_test_verifier",
        ),
    )
    client.app.state.work_order_evidence_verifiers = registry

    response = client.post(
        f"/agent/work-orders/plans/{plan_id}/evidence/evaluate",
        json={"evidence": [_reference(plan_digest)]},
    )

    assert response.status_code == 200
    report = response.json()["report"]
    assert report["decision"] == "accept"
    assert report["criteria"][0]["status"] == "passed"
    assert report["read_only"] is True
    assert report["execution_started"] is False
    assert report["permissions_changed"] is False


def test_work_order_evidence_api_does_not_accept_caller_supplied_status():
    client = authenticated_client()
    plan_id, plan_digest = _create_owned_plan(client)
    evidence = _reference(plan_digest)
    evidence["status"] = "passed"

    response = client.post(
        f"/agent/work-orders/plans/{plan_id}/evidence/evaluate",
        json={"evidence": [evidence]},
    )

    assert response.status_code == 422


def test_work_order_evidence_api_is_owner_scoped_and_hides_foreign_records():
    owner_client = authenticated_client()
    plan_id, plan_digest = _create_owned_plan(owner_client)
    foreign_client = authenticated_client()

    response = foreign_client.post(
        f"/agent/work-orders/plans/{plan_id}/evidence/evaluate",
        json={"evidence": [_reference(plan_digest)]},
    )

    assert response.status_code == 404


def test_work_order_evidence_api_rejects_malformed_digest():
    client = authenticated_client()
    plan_id, plan_digest = _create_owned_plan(client)
    evidence = _reference(plan_digest)
    evidence["evidence_digest"] = "not-a-digest"

    response = client.post(
        f"/agent/work-orders/plans/{plan_id}/evidence/evaluate",
        json={"evidence": [evidence]},
    )

    assert response.status_code == 422
