"""Identity-aware workflow planning, recovery, and resume regression tests."""

import pytest
from pydantic import ValidationError

from mrhub.agents.core import AgentCore, AgentPlanRequest
from mrhub.agents.workflow_runner import AgentWorkflowRunner
from mrhub.api.routes.agent import WorkflowReconciliationRequest
from mrhub.domain.tasks import TaskRecord, TaskStatus
from mrhub.infrastructure.database import TaskRepository
from mrhub.jobs.recovery import WorkflowRecoveryError, WorkflowRecoveryRepository
from mrhub.providers.router import ModelRouter
from mrhub.providers.stub import StubProvider
from mrhub.tools.builtins import build_tool_registry


def make_core():
    router = ModelRouter()
    router.register_provider(StubProvider())
    return AgentCore(router, build_tool_registry())


def make_recovery(tmp_path):
    tasks = TaskRepository(tmp_path / "workflow-identity.sqlite3")
    tasks.initialize()
    return tasks, WorkflowRecoveryRepository(tasks.database_path)


def test_explicit_step_identity_and_dependency_digest_survive_request_reordering():
    first = AgentPlanRequest(
        goal="Execute independent steps with stable identities",
        tools=[
            {
                "name": "text.echo",
                "payload": {"text": "alpha"},
                "step_id": "alpha",
                "depends_on": [],
            },
            {
                "name": "text.echo",
                "payload": {"text": "beta"},
                "step_id": "beta",
                "depends_on": [],
            },
        ],
    )
    reordered = AgentPlanRequest(
        goal=first.goal,
        tools=list(reversed(first.tools)),
    )

    assert AgentWorkflowRunner.request_digest(first) == AgentWorkflowRunner.request_digest(
        reordered
    )
    assert {step.step_id for step in first.workflow_steps()} == {
        "step-1",
        "alpha",
        "beta",
    }


def test_duplicate_stable_step_id_is_rejected():
    with pytest.raises(ValidationError):
        AgentPlanRequest(
            goal="Reject duplicate workflow identity",
            tools=[
                {
                    "name": "text.echo",
                    "step_id": "duplicate",
                    "depends_on": [],
                },
                {
                    "name": "text.echo",
                    "step_id": "duplicate",
                    "depends_on": [],
                },
            ],
        )


def test_core_skips_already_succeeded_step_by_identity(monkeypatch):
    core = make_core()
    request = AgentPlanRequest(
        goal="Skip a completed step using its stable identity",
        tools=[
            {
                "name": "text.echo",
                "payload": {"text": "already done"},
                "step_id": "completed",
                "depends_on": [],
            },
            {
                "name": "text.echo",
                "payload": {"text": "execute now"},
                "step_id": "pending",
                "depends_on": [],
            },
        ],
    )
    invoked = []
    original_invoke = core.tool_registry.invoke

    def tracking_invoke(name, payload, **kwargs):
        invoked.append(payload["text"])
        return original_invoke(name, payload, **kwargs)

    monkeypatch.setattr(core.tool_registry, "invoke", tracking_invoke)
    response = core.execute(request, skip_step_ids={"completed"})

    assert response["execution_completed"] is True
    assert invoked == ["execute now"]


def test_recovery_gates_steps_by_identity_and_dependency_status(tmp_path):
    _tasks, recovery = make_recovery(tmp_path)
    workflow_id = recovery.create_run(
        "a" * 64,
        [
            {
                "step_number": 1,
                "step_key": "step-1",
                "depends_on": [],
                "kind": "provider_selection",
                "name": "provider",
            },
            {
                "step_number": 2,
                "step_key": "alpha",
                "depends_on": ["step-1"],
                "kind": "safe_tool",
                "name": "text.echo",
            },
            {
                "step_number": 3,
                "step_key": "beta",
                "depends_on": ["alpha"],
                "kind": "safe_tool",
                "name": "text.echo",
            },
        ],
        definition_version=3,
    )
    recovery.start_run(workflow_id)
    provider = recovery.start_step(workflow_id, "step-1")
    recovery.complete_step(workflow_id, provider, "b" * 64)

    alpha = recovery.start_step(workflow_id, "alpha")
    recovery.complete_step(workflow_id, alpha, "c" * 64)

    with pytest.raises(WorkflowRecoveryError, match="not eligible"):
        recovery.start_step(workflow_id, "alpha")

    beta = recovery.start_step(workflow_id, "beta")
    assert beta.step_key == "beta"


def test_failed_dependency_blocks_descendants_and_unknown_outcome_requires_reconciliation(
    tmp_path,
):
    _tasks, recovery = make_recovery(tmp_path)
    workflow_id = recovery.create_run(
        "d" * 64,
        [
            {
                "step_number": 1,
                "step_key": "step-1",
                "depends_on": [],
                "kind": "provider_selection",
                "name": "provider",
            },
            {
                "step_number": 2,
                "step_key": "external",
                "depends_on": ["step-1"],
                "kind": "external_tool",
                "name": "custom.external",
            },
            {
                "step_number": 3,
                "step_key": "dependent",
                "depends_on": ["external"],
                "kind": "safe_tool",
                "name": "text.echo",
            },
        ],
        definition_version=3,
    )
    recovery.start_run(workflow_id)
    provider = recovery.start_step(workflow_id, "step-1")
    recovery.complete_step(workflow_id, provider, "e" * 64)
    external = recovery.start_step(workflow_id, "external")
    recovery.fail_step(
        workflow_id,
        external,
        "external_result_uncertain",
        unknown_outcome=True,
    )

    before = recovery.get_run(workflow_id)
    assert before is not None
    assert before["steps"][2]["dependency_state"] == "blocked"
    decision = recovery.resume_decision(
        workflow_id, "d" * 64, definition_version=3
    )
    assert decision.decision == "reconcile"
    assert decision.next_step_id == "external"

    recovery.resolve_unknown_step(
        workflow_id,
        "external",
        "succeeded",
        output_digest="f" * 64,
    )
    after = recovery.get_run(workflow_id)
    assert after is not None
    assert after["steps"][2]["dependency_state"] == "ready"
    next_decision = recovery.resume_decision(
        workflow_id, "d" * 64, definition_version=3
    )
    assert next_decision.decision == "resume"
    assert next_decision.next_step_id == "dependent"


def test_runner_resume_after_reordering_does_not_replay_succeeded_identity(
    tmp_path, monkeypatch
):
    task_repository = TaskRepository(tmp_path / "workflow-runner-identity.sqlite3")
    task_repository.initialize()
    core = make_core()
    runner = AgentWorkflowRunner(task_repository, core)
    owner = "identity-resume-test-owner"
    with task_repository._connection() as connection:
        connection.execute(
            """
            INSERT INTO auth_users (
                user_id, username, salt, password_hash, created_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (owner, owner, "00", "00", "2026-11-23T00:00:00+00:00"),
        )
    original_request = AgentPlanRequest(
        goal="Resume by stable identity after harmless reordering",
        tools=[
            {
                "name": "text.echo",
                "payload": {"text": "do not replay"},
                "step_id": "first",
                "depends_on": [],
            },
            {
                "name": "text.echo",
                "payload": {"text": "execute after resume"},
                "step_id": "later",
                "depends_on": [],
            },
        ],
    )
    original_plan = core.plan(original_request)
    request_digest = AgentWorkflowRunner.request_digest(original_request)
    step_specs, _ = runner.build_durable_step_metadata(core, original_request, original_plan)
    task = TaskRecord(
        task_type="agent.workflow",
        description="Stable identity resume regression",
    )
    workflow_id = runner.recovery.create_run(
        request_digest,
        step_specs,
        task=task,
        definition_version=3,
        owner_user_id=owner,
    )

    runner.jobs.transition(task.task_id, TaskStatus.RUNNING)
    lease = runner.lease_manager.acquire(str(task.task_id), runner.worker_id)
    assert lease is not None
    runner.recovery.start_run(workflow_id, lease=lease)
    provider = runner.recovery.start_step(workflow_id, "step-1", lease=lease)
    runner.recovery.complete_step(
        workflow_id,
        provider,
        runner._digest(original_plan["selected_provider"]),
        lease=lease,
    )
    first = runner.recovery.start_step(workflow_id, "first", lease=lease)
    runner.recovery.complete_step(
        workflow_id, first, "1" * 64, lease=lease
    )
    assert runner.recovery.mark_interrupted(workflow_id, lease=lease) == 0
    runner.jobs.transition(task.task_id, TaskStatus.WAITING_APPROVAL, lease=lease)
    assert runner.lease_manager.release(lease) is True

    reordered_request = AgentPlanRequest(
        goal=original_request.goal,
        tools=list(reversed(original_request.tools)),
    )
    reordered_plan = core.plan(reordered_request)
    assert AgentWorkflowRunner.request_digest(reordered_request) == request_digest

    invoked = []
    original_invoke = core.tool_registry.invoke

    def tracking_invoke(name, payload, **kwargs):
        invoked.append(payload["text"])
        return original_invoke(name, payload, **kwargs)

    monkeypatch.setattr(core.tool_registry, "invoke", tracking_invoke)
    result = runner.resume(
        workflow_id,
        reordered_request,
        reordered_plan,
        request_digest,
        owner,
    )

    assert invoked == ["execute after resume"]
    assert result["execution"]["execution_completed"] is True
    assert result["workflow"]["status"] == "succeeded"
    persisted = {step["step_key"]: step["status"] for step in result["workflow"]["steps"]}
    assert persisted == {
        "step-1": "succeeded",
        "first": "succeeded",
        "later": "succeeded",
    }


def test_cancelling_running_step_blocks_its_pending_descendants(tmp_path):
    _tasks, recovery = make_recovery(tmp_path)
    workflow_id = recovery.create_run(
        "9" * 64,
        [
            {
                "step_number": 1,
                "step_key": "step-1",
                "depends_on": [],
                "kind": "provider_selection",
                "name": "provider",
            },
            {
                "step_number": 2,
                "step_key": "active",
                "depends_on": ["step-1"],
                "kind": "safe_tool",
                "name": "text.echo",
            },
            {
                "step_number": 3,
                "step_key": "descendant",
                "depends_on": ["active"],
                "kind": "safe_tool",
                "name": "text.echo",
            },
        ],
        definition_version=3,
    )
    recovery.start_run(workflow_id)
    provider = recovery.start_step(workflow_id, "step-1")
    recovery.complete_step(workflow_id, provider, "8" * 64)
    recovery.start_step(workflow_id, "active")

    recovery.finish_run(workflow_id, "cancelled")
    stored = recovery.get_run(workflow_id)

    assert stored is not None
    states = {step["step_key"]: step for step in stored["steps"]}
    assert stored["status"] == "cancelled"
    assert states["active"]["status"] == "cancelled"
    assert states["descendant"]["status"] == "cancelled"
    assert states["descendant"]["dependency_state"] == "blocked"


def test_reconciliation_api_accepts_stable_identity_and_legacy_position():
    stable = WorkflowReconciliationRequest(
        step_id="external",
        outcome="succeeded",
        output_digest="a" * 64,
    )
    legacy = WorkflowReconciliationRequest(
        step_number=2,
        outcome="failed",
    )

    assert stable.resolved_step_identity() == "external"
    assert legacy.resolved_step_identity() == 2


@pytest.mark.parametrize(
    "payload",
    [
        {"outcome": "failed"},
        {"step_id": "external", "step_number": 2, "outcome": "failed"},
    ],
    ids=["missing-identity", "ambiguous-identity"],
)
def test_reconciliation_api_rejects_missing_or_ambiguous_identity(payload):
    with pytest.raises(ValidationError):
        WorkflowReconciliationRequest(**payload)


def test_queued_workflow_cancellation_terminalizes_all_pending_steps(tmp_path):
    tasks, recovery = make_recovery(tmp_path)
    owner = "queued-cancellation-owner"
    with tasks._connection() as connection:
        connection.execute(
            """
            INSERT INTO auth_users (
                user_id, username, salt, password_hash, created_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (owner, owner, "00", "00", "2026-11-23T00:00:00+00:00"),
        )
    workflow_id = recovery.create_run(
        "7" * 64,
        [
            {
                "step_number": 1,
                "step_key": "step-1",
                "depends_on": [],
                "kind": "provider_selection",
                "name": "provider",
            },
            {
                "step_number": 2,
                "step_key": "child",
                "depends_on": ["step-1"],
                "kind": "safe_tool",
                "name": "text.echo",
            },
        ],
        task=TaskRecord(
            task_type="agent.workflow",
            description="Queued cancellation regression",
        ),
        owner_user_id=owner,
        definition_version=3,
    )

    result = recovery.request_cancellation(workflow_id, owner_user_id=owner)
    stored = recovery.get_run(workflow_id, owner_user_id=owner)

    assert result["status"] == "cancelled"
    assert stored is not None
    assert stored["status"] == "cancelled"
    assert all(step["status"] == "cancelled" for step in stored["steps"])
    assert stored["steps"][1]["dependency_state"] == "blocked"
