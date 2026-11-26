from mrhub.agents.work_order_evidence import (
    EvidenceReference,
    EvidenceVerification,
    EvidenceVerifierRegistry,
    VerifierStatus,
    WorkOrderCriterion,
    WorkOrderDecision,
    WorkOrderSnapshot,
    evaluate_work_order_evidence,
)
from mrhub.agents.workflow_evidence import verify_workflow_step_evidence

WORK_ORDER_DIGEST = "a" * 64
OUTPUT_DIGEST = "b" * 64
WORKFLOW_ID = "123e4567-e89b-12d3-a456-426614174000"


class FakeWorkflowRepository:
    def __init__(self, step, *, owner="owner-a"):
        self.step = step
        self.owner = owner

    def get_run(self, workflow_id, *, owner_user_id):
        assert str(workflow_id) == WORKFLOW_ID
        if owner_user_id != self.owner:
            return None
        return {"steps": [self.step]}


class FakePlanRecord:
    status = "consumed"
    workflow_id = WORKFLOW_ID


class FakePlanRepository:
    def __init__(self, *, workflow_id=WORKFLOW_ID, status="consumed"):
        self.record = FakePlanRecord()
        self.record.workflow_id = workflow_id
        self.record.status = status

    def get(self, plan_id, *, owner_user_id):
        if plan_id != "plan-example" or owner_user_id != "owner-a":
            return None
        return self.record


def _criterion(**changes):
    values = {
        "criterion_id": "ac_001",
        "required": True,
        "description": "workflow_step_succeeded:step-2",
        "step_capability_bindings": (("step-2", ("text.echo",)),),
    }
    values.update(changes)
    return WorkOrderCriterion(**values)


def _reference(**changes):
    values = {
        "evidence_id": "evidence_step_001",
        "criterion_id": "ac_001",
        "source_type": "agent_workflow_step",
        "source_ref": f"{WORKFLOW_ID}/step-2",
        "evidence_digest": OUTPUT_DIGEST,
        "work_order_digest": WORK_ORDER_DIGEST,
        "work_order_revision": 1,
        "observed_at": "2026-11-27T12:00:00+00:00",
        "verifier_id": "hub.workflow_step.v1",
        "owner_user_id": "owner-a",
        "plan_id": "plan-example",
    }
    values.update(changes)
    return EvidenceReference(**values)


def _step(**changes):
    value = {
        "step_key": "step-2",
        "step_name": "text.echo",
        "status": "succeeded",
        "output_digest": OUTPUT_DIGEST,
        "attempt_count": 1,
        "started_at": "2026-11-27T12:00:00+00:00",
        "finished_at": "2026-11-27T12:00:01+00:00",
        "error_code": None,
    }
    value.update(changes)
    return value


def _registry(repository, plan_repository=None):
    registry = EvidenceVerifierRegistry()
    registry.register(
        source_type="agent_workflow_step",
        verifier_id="hub.workflow_step.v1",
        verifier=lambda reference, criterion: verify_workflow_step_evidence(
            reference,
            criterion,
            repository=repository,
            plan_repository=plan_repository or FakePlanRepository(),
        ),
    )
    return registry


def test_exact_owner_workflow_step_and_awiplan_capability_can_verify_criterion():
    report = evaluate_work_order_evidence(
        WorkOrderSnapshot(
            work_order_id="wo_example",
            revision=1,
            digest=WORK_ORDER_DIGEST,
            criteria=(_criterion(),),
        ),
        (_reference(),),
        _registry(FakeWorkflowRepository(_step())),
    )

    assert report.decision is WorkOrderDecision.ACCEPT
    assert report.criteria[0].status.value == "passed"
    assert report.as_dict()["execution_started"] is False


def test_unowned_workflow_step_remains_unknown():
    report = evaluate_work_order_evidence(
        WorkOrderSnapshot(
            work_order_id="wo_example",
            revision=1,
            digest=WORK_ORDER_DIGEST,
            criteria=(_criterion(),),
        ),
        (_reference(),),
        _registry(FakeWorkflowRepository(_step(), owner="owner-b")),
    )

    assert report.decision is WorkOrderDecision.REVIEW_REQUIRED
    assert "workflow_not_found_or_not_owned" in report.criteria[0].reason_codes


def test_step_capability_mismatch_remains_unknown():
    report = evaluate_work_order_evidence(
        WorkOrderSnapshot(
            work_order_id="wo_example",
            revision=1,
            digest=WORK_ORDER_DIGEST,
            criteria=(_criterion(),),
        ),
        (_reference(),),
        _registry(FakeWorkflowRepository(_step(step_name="different.tool"))),
    )

    assert report.decision is WorkOrderDecision.REVIEW_REQUIRED
    assert "workflow_step_capability_mismatch" in report.criteria[0].reason_codes


def test_step_id_must_be_declared_by_the_exact_awiplan_step():
    report = evaluate_work_order_evidence(
        WorkOrderSnapshot(
            work_order_id="wo_example",
            revision=1,
            digest=WORK_ORDER_DIGEST,
            criteria=(_criterion(step_capability_bindings=(("another-step", ("text.echo",)),)),),
        ),
        (_reference(),),
        _registry(FakeWorkflowRepository(_step())),
    )

    assert report.decision is WorkOrderDecision.REVIEW_REQUIRED
    assert "criterion_step_not_in_plan" in report.criteria[0].reason_codes


def test_non_terminal_workflow_step_remains_unknown():
    report = evaluate_work_order_evidence(
        WorkOrderSnapshot(
            work_order_id="wo_example",
            revision=1,
            digest=WORK_ORDER_DIGEST,
            criteria=(_criterion(),),
        ),
        (_reference(),),
        _registry(FakeWorkflowRepository(_step(status="running"))),
    )

    assert report.decision is WorkOrderDecision.REVIEW_REQUIRED
    assert "workflow_step_not_terminal" in report.criteria[0].reason_codes


def test_failed_workflow_step_returns_digest_bound_failure():
    failed = _step(
        status="failed",
        output_digest=None,
        error_code="tool_execution_failed",
    )
    result = verify_workflow_step_evidence(
        _reference(),
        _criterion(),
        repository=FakeWorkflowRepository(failed),

        plan_repository=FakePlanRepository(),
    )

    assert isinstance(result, EvidenceVerification)
    assert result.status is VerifierStatus.FAILED
    assert isinstance(result.evidence_digest, str)
    assert len(result.evidence_digest) == 64


def test_workflow_evidence_requires_internal_owner_context():
    result = verify_workflow_step_evidence(
        _reference(owner_user_id=None),
        _criterion(),
        repository=FakeWorkflowRepository(_step()),

        plan_repository=FakePlanRepository(),
    )

    assert result.status is VerifierStatus.UNKNOWN
    assert result.reason_code == "evidence_owner_context_missing"



def test_workflow_step_cannot_verify_evidence_for_a_different_or_unconsumed_plan():
    result = verify_workflow_step_evidence(
        _reference(),
        _criterion(),
        repository=FakeWorkflowRepository(_step()),
        plan_repository=FakePlanRepository(workflow_id="123e4567-e89b-12d3-a456-426614174001"),
    )

    assert result.status is VerifierStatus.UNKNOWN
    assert result.reason_code == "workflow_not_bound_to_work_order_plan"

    unconsumed = verify_workflow_step_evidence(
        _reference(),
        _criterion(),
        repository=FakeWorkflowRepository(_step()),
        plan_repository=FakePlanRepository(status="active"),
    )

    assert unconsumed.status is VerifierStatus.UNKNOWN
    assert unconsumed.reason_code == "workflow_not_bound_to_work_order_plan"
