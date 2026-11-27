from __future__ import annotations

import secrets
from uuid import uuid4

from client_helpers import authenticated_client
from mrhub.agents.awi_planner import ExecutionPlan, PlanStep
from mrhub.agents.plan_repository import AgentWorkOrderPlanRepository
from mrhub.agents.work_order import WorkOrder
from mrhub.agents.work_order_evidence import (
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
from mrhub.security.auth import AuthService, _password_digest


def _create_owned_plan(
    client,
    *,
    work_order_revision: int = 1,
    plan_revision: int = 1,
    persist_revisions: bool = False,
    stored_work_order_digest: str | None = None,
) -> tuple[str, str, str]:
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
    work_order_payload = {"work_order": work_order.model_dump(mode="json")}
    work_order_digest = _canonical_plan_digest(work_order_payload)
    payload = {
        "work_order": work_order.model_dump(mode="json"),
        "plan": plan.model_dump(mode="json"),
    }
    if persist_revisions:
        payload.update(
            {
                "work_order_revision": work_order_revision,
                "plan_revision": plan_revision,
                "work_order_digest": (
                    stored_work_order_digest or work_order_digest
                ),
            }
        )
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
    return plan_id, digest, work_order_digest


def _reference(
    work_order_digest: str,
    *,
    work_order_revision: int = 1,
) -> dict[str, object]:
    return {
        "evidence_id": "evidence-001",
        "criterion_id": "ac_001",
        "source_type": "test.fixture",
        "source_ref": "test-runs/123/checks/1",
        "evidence_digest": "b" * 64,
        "work_order_digest": work_order_digest,
        "work_order_revision": work_order_revision,
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
    plan_id, plan_digest, work_order_digest = _create_owned_plan(client)

    response = client.post(
        f"/agent/work-orders/plans/{plan_id}/evidence/evaluate",
        json={"evidence": [_reference(work_order_digest)]},
    )

    assert response.status_code == 200
    body = response.json()
    report = body["report"]
    assert report["decision"] == "review_required"
    assert report["criteria"][0]["status"] == "unknown"
    assert "unregistered_verifier" in report["criteria"][0]["reason_codes"]
    assert body["plan_digest"] == plan_digest
    assert body["work_order_digest"] == work_order_digest
    assert body["work_order_revision"] == 1
    assert body["plan_revision"] == 1
    assert body["report"]["work_order_digest"] == work_order_digest
    assert body["report"]["work_order_revision"] == 1
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
    plan_id, _plan_digest, work_order_digest = _create_owned_plan(client)
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
        json={"evidence": [_reference(work_order_digest)]},
    )

    assert response.status_code == 200
    report = response.json()["report"]
    assert report["decision"] == "accept"
    assert report["criteria"][0]["status"] == "passed"
    assert report["read_only"] is True
    assert report["execution_started"] is False
    assert report["permissions_changed"] is False


def test_plan_creation_persists_revision_metadata_in_encrypted_record(monkeypatch):
    client = authenticated_client()
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
    planned = {
        "work_order": work_order.model_dump(mode="json"),
        "plan": plan.model_dump(mode="json"),
        "decision_analysis": {},
        "planning_assessment": {},
        "model_selection": {},
        "prompt_templates": {},
        "capability_assessment": {},
    }
    monkeypatch.setattr(
        "mrhub.api.routes.agent.create_goal_work_order_plan",
        lambda request, current_user: planned,
    )

    created = client.post(
        "/agent/work-orders/plans",
        json={"goal": "Review one local build result"},
    )

    assert created.status_code == 200
    body = created.json()
    expected_digest = _canonical_plan_digest(
        {"work_order": work_order.model_dump(mode="json")}
    )
    assert body["work_order_revision"] == 1
    assert body["plan_revision"] == 1
    assert body["work_order_digest"] == expected_digest

    evaluated = client.post(
        f"/agent/work-orders/plans/{body['plan_id']}/evidence/evaluate",
        json={"evidence": []},
    )

    assert evaluated.status_code == 200
    evidence_body = evaluated.json()
    assert evidence_body["work_order_revision"] == 1
    assert evidence_body["plan_revision"] == 1
    assert evidence_body["work_order_digest"] == expected_digest
    assert evidence_body["report"]["work_order_revision"] == 1
    assert evidence_body["report"]["work_order_digest"] == expected_digest


def test_work_order_evidence_api_uses_persisted_non_default_revisions():
    client = authenticated_client()
    plan_id, _plan_digest, work_order_digest = _create_owned_plan(
        client,
        work_order_revision=3,
        plan_revision=7,
        persist_revisions=True,
    )

    fetched = client.get(f"/agent/work-orders/plans/{plan_id}")
    assert fetched.status_code == 200
    assert fetched.json()["work_order_revision"] == 3
    assert fetched.json()["plan_revision"] == 7
    assert fetched.json()["work_order_digest"] == work_order_digest

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
        json={
            "evidence": [
                _reference(work_order_digest, work_order_revision=3)
            ]
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["work_order_revision"] == 3
    assert body["plan_revision"] == 7
    assert body["report"]["work_order_revision"] == 3
    assert body["report"]["work_order_digest"] == work_order_digest
    assert body["report"]["decision"] == "accept"


def test_work_order_evidence_api_marks_prior_revision_evidence_stale():
    client = authenticated_client()
    plan_id, _plan_digest, work_order_digest = _create_owned_plan(
        client,
        work_order_revision=3,
        plan_revision=7,
        persist_revisions=True,
    )

    response = client.post(
        f"/agent/work-orders/plans/{plan_id}/evidence/evaluate",
        json={
            "evidence": [
                _reference(work_order_digest, work_order_revision=2)
            ]
        },
    )

    assert response.status_code == 200
    report = response.json()["report"]
    assert report["decision"] == "review_required"
    assert report["work_order_revision"] == 3
    assert report["criteria"][0]["status"] == "stale"
    assert "stale_work_order_reference" in report["criteria"][0]["reason_codes"]


def test_work_order_evidence_api_rejects_mismatched_persisted_work_order_digest():
    client = authenticated_client()
    plan_id, _plan_digest, _work_order_digest = _create_owned_plan(
        client,
        work_order_revision=3,
        plan_revision=7,
        persist_revisions=True,
        stored_work_order_digest="f" * 64,
    )

    response = client.get(f"/agent/work-orders/plans/{plan_id}")

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "Plan record failed integrity or schema validation"
    )


def test_work_order_evidence_api_does_not_accept_caller_supplied_status():
    client = authenticated_client()
    plan_id, _plan_digest, work_order_digest = _create_owned_plan(client)
    evidence = _reference(work_order_digest)
    evidence["status"] = "passed"

    response = client.post(
        f"/agent/work-orders/plans/{plan_id}/evidence/evaluate",
        json={"evidence": [evidence]},
    )

    assert response.status_code == 422


def test_work_order_evidence_api_is_owner_scoped_and_hides_foreign_records():
    owner_client = authenticated_client()
    plan_id, _plan_digest, work_order_digest = _create_owned_plan(owner_client)

    # Create a second authenticated identity in the SAME database so this
    # proves owner isolation rather than merely testing a missing record.
    settings = get_settings()
    repository = TaskRepository(settings.database_path)
    salt = secrets.token_bytes(16)
    repository.create_auth_user(
        "foreign-user",
        "foreign",
        salt.hex(),
        _password_digest("foreign-test-password-2026", salt).hex(),
    )
    foreign_login = AuthService(repository).login("foreign", "foreign-test-password-2026")
    assert foreign_login is not None

    from fastapi.testclient import TestClient

    from mrhub.main import create_app

    foreign_client = TestClient(create_app())
    foreign_client.headers.update(
        {"Authorization": f"Bearer {foreign_login[0]}"}
    )
    response = foreign_client.post(
        f"/agent/work-orders/plans/{plan_id}/evidence/evaluate",
        json={"evidence": [_reference(work_order_digest)]},
    )

    assert response.status_code == 404


def test_work_order_evidence_api_rejects_malformed_digest():
    client = authenticated_client()
    plan_id, _plan_digest, work_order_digest = _create_owned_plan(client)
    evidence = _reference(work_order_digest)
    evidence["evidence_digest"] = "not-a-digest"

    response = client.post(
        f"/agent/work-orders/plans/{plan_id}/evidence/evaluate",
        json={"evidence": [evidence]},
    )

    assert response.status_code == 422
