from concurrent.futures import ThreadPoolExecutor
from uuid import UUID

import pytest

from mrhub.domain.tasks import TaskRecord, TaskStatus
from mrhub.infrastructure.database import TaskRepository
from mrhub.jobs.engine import JobEngine
from mrhub.jobs.leases import LeaseManager
from mrhub.jobs.recovery import (
    RecoveryRequired,
    WorkflowRecoveryError,
    WorkflowRecoveryRepository,
)


def make_repository(tmp_path):
    tasks = TaskRepository(tmp_path / "workflow-recovery.sqlite3")
    tasks.initialize()
    return WorkflowRecoveryRepository(tasks.database_path)


def make_run(repository, *, request_digest="a" * 64, definition_version=1):
    return repository.create_run(
        request_digest,
        [
            {"step_number": 1, "kind": "provider_selection", "name": "provider"},
            {"step_number": 2, "kind": "tool", "name": "text.echo"},
            {"step_number": 3, "kind": "tool", "name": "text.format"},
        ],
        definition_version=definition_version,
    )


def test_checkpoint_is_created_only_after_validated_step_completion(tmp_path):
    repository = make_repository(tmp_path)
    workflow_id = make_run(repository)
    assert repository.latest_checkpoint(workflow_id) is None

    repository.start_run(workflow_id)
    attempt = repository.start_step(workflow_id, 1)
    checkpoint = repository.complete_step(workflow_id, attempt, "b" * 64)

    assert checkpoint.checkpoint_version == 1
    assert checkpoint.step_number == 1
    assert len(checkpoint.state_digest) == 64
    assert repository.latest_checkpoint(workflow_id) == checkpoint


def test_each_completed_step_advances_digest_only_checkpoint(tmp_path):
    repository = make_repository(tmp_path)
    workflow_id = make_run(repository)
    repository.start_run(workflow_id)

    first = repository.start_step(workflow_id, 1)
    checkpoint_one = repository.complete_step(workflow_id, first, "b" * 64)
    second = repository.start_step(workflow_id, 2)
    checkpoint_two = repository.complete_step(workflow_id, second, "c" * 64)

    assert checkpoint_two.checkpoint_version == checkpoint_one.checkpoint_version + 1
    assert checkpoint_two.step_number == 2
    assert checkpoint_two.state_digest != checkpoint_one.state_digest


def test_completed_step_cannot_be_replayed(tmp_path):
    repository = make_repository(tmp_path)
    workflow_id = make_run(repository)
    repository.start_run(workflow_id)
    attempt = repository.start_step(workflow_id, 1)
    repository.complete_step(workflow_id, attempt, "d" * 64)

    with pytest.raises(WorkflowRecoveryError, match="not eligible"):
        repository.start_step(workflow_id, 1)


def test_workflow_steps_must_execute_in_order(tmp_path):
    repository = make_repository(tmp_path)
    workflow_id = make_run(repository)
    repository.start_run(workflow_id)

    with pytest.raises(WorkflowRecoveryError, match="Earlier workflow steps"):
        repository.start_step(workflow_id, 2)


def test_resume_decision_starts_at_first_incomplete_step(tmp_path):
    repository = make_repository(tmp_path)
    workflow_id = make_run(repository)
    repository.start_run(workflow_id)
    first = repository.start_step(workflow_id, 1)
    repository.complete_step(workflow_id, first, "e" * 64)

    decision = repository.resume_decision(workflow_id, "a" * 64)

    assert decision.decision == "resume"
    assert decision.next_step == 2
    assert decision.checkpoint_version == 1


def test_request_digest_mismatch_requires_input_again(tmp_path):
    repository = make_repository(tmp_path)
    workflow_id = make_run(repository)

    decision = repository.resume_decision(workflow_id, "f" * 64)

    assert decision.decision == "request_input"
    assert decision.reason_code == "request_digest_mismatch"


def test_workflow_definition_mismatch_requires_replanning(tmp_path):
    repository = make_repository(tmp_path)
    workflow_id = make_run(repository, definition_version=2)

    decision = repository.resume_decision(
        workflow_id, "a" * 64, definition_version=1
    )

    assert decision.decision == "replan"
    assert decision.reason_code == "definition_version_mismatch"


def test_interrupted_step_is_marked_unknown_and_never_replayed(tmp_path):
    repository = make_repository(tmp_path)
    workflow_id = make_run(repository)
    repository.start_run(workflow_id)
    safe_attempt = repository.start_step(workflow_id, 1)
    repository.complete_step(workflow_id, safe_attempt, "b" * 64)
    repository.start_step(workflow_id, 2)

    assert repository.mark_interrupted(workflow_id) == 1
    run = repository.get_run(workflow_id)
    assert run is not None
    assert run["status"] == "recovery_required"
    assert run["steps"][1]["status"] == "unknown_outcome"

    decision = repository.resume_decision(workflow_id, "a" * 64)
    assert decision.decision == "reconcile"
    assert decision.reason_code == "worker_interrupted"
    with pytest.raises(RecoveryRequired):
        repository.start_step(workflow_id, 2)


def test_unknown_outcome_requires_explicit_reconciliation_before_resume(tmp_path):
    repository = make_repository(tmp_path)
    workflow_id = make_run(repository)
    repository.start_run(workflow_id)
    attempt = repository.start_step(workflow_id, 1)
    repository.fail_step(
        workflow_id, attempt, "external_result_uncertain", unknown_outcome=True
    )

    with pytest.raises(RecoveryRequired):
        repository.start_step(workflow_id, 1)

    checkpoint = repository.resolve_unknown_step(
        workflow_id, 1, "succeeded", output_digest="1" * 64
    )
    assert checkpoint is not None
    decision = repository.resume_decision(workflow_id, "a" * 64)
    assert decision.decision == "resume"
    assert decision.next_step == 2


def test_reconciled_failure_is_terminal_and_does_not_replay(tmp_path):
    repository = make_repository(tmp_path)
    workflow_id = make_run(repository)
    repository.start_run(workflow_id)
    attempt = repository.start_step(workflow_id, 1)
    repository.fail_step(
        workflow_id, attempt, "external_result_uncertain", unknown_outcome=True
    )

    assert repository.resolve_unknown_step(workflow_id, 1, "failed") is None
    decision = repository.resume_decision(workflow_id, "a" * 64)
    assert decision.decision == "terminal"
    assert decision.reason_code == "failed"


def test_known_step_failure_marks_workflow_failed(tmp_path):
    repository = make_repository(tmp_path)
    workflow_id = make_run(repository)
    repository.start_run(workflow_id)
    attempt = repository.start_step(workflow_id, 1)
    repository.fail_step(workflow_id, attempt, "validation_failed")

    decision = repository.resume_decision(workflow_id, "a" * 64)
    assert decision.decision == "terminal"
    assert decision.reason_code == "failed"


def test_workflow_cannot_finish_until_every_step_succeeds(tmp_path):
    repository = make_repository(tmp_path)
    workflow_id = make_run(repository)
    repository.start_run(workflow_id)

    with pytest.raises(WorkflowRecoveryError, match="Every workflow step"):
        repository.finish_run(workflow_id, "succeeded")


def test_concurrent_step_claim_creates_only_one_active_attempt(tmp_path):
    repository = make_repository(tmp_path)
    workflow_id = make_run(repository)
    repository.start_run(workflow_id)

    def attempt_start(_):
        try:
            return repository.start_step(workflow_id, 1)
        except WorkflowRecoveryError:
            return None

    with ThreadPoolExecutor(max_workers=6) as executor:
        attempts = list(executor.map(attempt_start, range(6)))

    winners = [attempt for attempt in attempts if attempt is not None]
    assert len(winners) == 1
    run = repository.get_run(workflow_id)
    assert run is not None
    assert run["steps"][0]["attempt_count"] == 1


def test_recovery_metadata_does_not_expose_step_payloads_or_outputs(tmp_path):
    repository = make_repository(tmp_path)
    workflow_id = make_run(repository)
    run = repository.get_run(workflow_id)

    assert run is not None
    assert run["stored_request"] is False
    assert run["stored_step_payloads"] is False
    assert run["stored_step_outputs"] is False
    assert "payload" not in run["steps"][0]
    assert "output" not in run["steps"][0]


def test_recovery_rejects_invalid_digests_and_error_codes(tmp_path):
    repository = make_repository(tmp_path)
    with pytest.raises(WorkflowRecoveryError):
        repository.create_run("not-a-digest", [{"step_number": 1, "kind": "tool", "name": "x"}])

    workflow_id = make_run(repository)
    repository.start_run(workflow_id)
    attempt = repository.start_step(workflow_id, 1)
    with pytest.raises(WorkflowRecoveryError):
        repository.complete_step(workflow_id, attempt, "not-a-digest")
    with pytest.raises(WorkflowRecoveryError):
        repository.fail_step(workflow_id, attempt, "raw exception text with spaces")


def test_run_lookup_returns_only_bounded_recovery_metadata(tmp_path):
    repository = make_repository(tmp_path)
    workflow_id = make_run(repository)
    run = repository.get_run(UUID(str(workflow_id)))

    assert run is not None
    assert run["status"] == "queued"
    assert run["current_step"] == 0
    assert len(run["steps"]) == 3



def test_workflow_step_commit_is_fenced_against_expired_owner(tmp_path):
    database_path = tmp_path / "workflow-lease-fence.sqlite3"
    tasks = TaskRepository(database_path)
    tasks.initialize()
    recovery = WorkflowRecoveryRepository(database_path)
    task = TaskRecord(task_type="agent.workflow", description="leased workflow")
    workflow_id = recovery.create_run(
        "a" * 64,
        [{"step_number": 1, "kind": "tool", "name": "text.echo"}],
        task=task,
    )
    jobs = JobEngine(tasks)
    jobs.transition(task.task_id, TaskStatus.RUNNING)
    leases = LeaseManager(database_path)
    old_lease = leases.acquire(str(task.task_id), "old-runner")
    assert old_lease is not None
    recovery.start_run(workflow_id, lease=old_lease)
    attempt = recovery.start_step(workflow_id, 1, lease=old_lease)

    with tasks._connection() as connection:
        connection.execute(
            "UPDATE worker_executions SET lease_expires_at = ? WHERE task_id = ?",
            ("2000-01-01T00:00:00+00:00", str(task.task_id)),
        )
    successor = leases.acquire(str(task.task_id), "successor-runner")
    assert successor is not None
    assert successor.fencing_token > old_lease.fencing_token

    with pytest.raises(RecoveryRequired, match="lease was lost"):
        recovery.complete_step(
            workflow_id, attempt, "b" * 64, lease=old_lease
        )
    assert recovery.latest_checkpoint(workflow_id) is None

    assert recovery.mark_interrupted(workflow_id, lease=successor) == 1
    decision = recovery.resume_decision(workflow_id, "a" * 64)
    assert decision.decision == "reconcile"


def test_task_linked_workflow_cannot_start_without_worker_lease(tmp_path):
    database_path = tmp_path / "workflow-start-requires-lease.sqlite3"
    tasks = TaskRepository(database_path)
    tasks.initialize()
    recovery = WorkflowRecoveryRepository(database_path)
    task = TaskRecord(task_type="agent.workflow", description="lease required")
    workflow_id = recovery.create_run(
        "a" * 64,
        [{"step_number": 1, "kind": "tool", "name": "text.echo"}],
        task=task,
    )

    with pytest.raises(RecoveryRequired, match="lease is required"):
        recovery.start_run(workflow_id)

    stored = recovery.get_run(workflow_id)
    assert stored is not None and stored["status"] == "queued"


@pytest.mark.parametrize(
    "mutation",
    ["start_step", "complete_step", "fail_step", "mark_interrupted", "finish_run"],
)
def test_task_linked_workflow_mutations_require_worker_lease(tmp_path, mutation):
    database_path = tmp_path / f"workflow-{mutation}-requires-lease.sqlite3"
    tasks = TaskRepository(database_path)
    tasks.initialize()
    recovery = WorkflowRecoveryRepository(database_path)
    task = TaskRecord(task_type="agent.workflow", description="lease required")
    workflow_id = recovery.create_run(
        "a" * 64,
        [{"step_number": 1, "kind": "tool", "name": "text.echo"}],
        task=task,
    )
    jobs = JobEngine(tasks)
    jobs.transition(task.task_id, TaskStatus.RUNNING)
    lease = LeaseManager(database_path).acquire(str(task.task_id), "test-worker")
    assert lease is not None
    recovery.start_run(workflow_id, lease=lease)

    attempt = None
    if mutation in {"complete_step", "fail_step", "mark_interrupted"}:
        attempt = recovery.start_step(workflow_id, 1, lease=lease)

    with pytest.raises(RecoveryRequired, match="lease is required"):
        if mutation == "start_step":
            recovery.start_step(workflow_id, 1)
        elif mutation == "complete_step":
            assert attempt is not None
            recovery.complete_step(workflow_id, attempt, "b" * 64)
        elif mutation == "fail_step":
            assert attempt is not None
            recovery.fail_step(workflow_id, attempt, "test_failure")
        elif mutation == "mark_interrupted":
            recovery.mark_interrupted(workflow_id)
        else:
            recovery.finish_run(workflow_id, "failed")

    stored = recovery.get_run(workflow_id)
    assert stored is not None and stored["status"] == "running"
    assert stored["steps"][0]["status"] == (
        "pending" if mutation == "start_step" or mutation == "finish_run" else "running"
    )
    assert recovery.latest_checkpoint(workflow_id) is None


def test_job_engine_rejects_terminal_transition_from_stale_workflow_lease(tmp_path):
    database_path = tmp_path / "job-lease-fence.sqlite3"
    tasks = TaskRepository(database_path)
    tasks.initialize()
    task = TaskRecord(task_type="agent.workflow", description="leased job")
    tasks.create(task)
    jobs = JobEngine(tasks)
    jobs.transition(task.task_id, TaskStatus.RUNNING)
    with tasks._connection() as connection:
        connection.execute(
            "INSERT INTO worker_executions (task_id, attempt_count) VALUES (?, 0)",
            (str(task.task_id),),
        )

    leases = LeaseManager(database_path)
    old_lease = leases.acquire(str(task.task_id), "old-job-runner")
    assert old_lease is not None
    with tasks._connection() as connection:
        connection.execute(
            "UPDATE worker_executions SET lease_expires_at = ? WHERE task_id = ?",
            ("2000-01-01T00:00:00+00:00", str(task.task_id)),
        )
    successor = leases.acquire(str(task.task_id), "new-job-runner")
    assert successor is not None

    with pytest.raises(RuntimeError, match="lease changed concurrently"):
        jobs.transition(task.task_id, TaskStatus.SUCCEEDED, lease=old_lease)
    stored = tasks.get(task.task_id)
    assert stored is not None and stored.status is TaskStatus.RUNNING



def test_interrupted_safe_step_becomes_retry_wait_not_unknown_outcome(tmp_path):
    repository = make_repository(tmp_path)
    workflow_id = repository.create_run(
        "a" * 64,
        [{"step_number": 1, "kind": "safe_tool", "name": "text.echo"}],
    )
    repository.start_run(workflow_id)
    repository.start_step(workflow_id, 1)

    assert repository.mark_interrupted(workflow_id) == 1
    run = repository.get_run(workflow_id)
    assert run is not None
    assert run["status"] == "paused"
    assert run["steps"][0]["status"] == "retry_wait"

    decision = repository.resume_decision(workflow_id, "a" * 64)
    assert decision.decision == "resume"
    assert decision.next_step == 1



def test_workflow_records_are_scoped_to_the_authenticated_owner(tmp_path):
    repository = make_repository(tmp_path)
    task = TaskRecord(task_type="agent.workflow", description="owned workflow")
    repository_database = TaskRepository(repository.database_path)
    repository_database.create_auth_user("user-a", "owner-a", "salt", "hash")
    workflow_id = repository.create_run(
        "a" * 64,
        [{"step_number": 1, "kind": "safe_tool", "name": "text.echo"}],
        task=task,
        owner_user_id="user-a",
    )

    assert repository.get_run(workflow_id, owner_user_id="user-a") is not None
    assert repository.get_run(workflow_id, owner_user_id="user-b") is None
    with pytest.raises(LookupError, match="Workflow not found"):
        repository.resume_decision(
            workflow_id, "a" * 64, owner_user_id="user-b"
        )
    with pytest.raises(LookupError, match="Workflow not found"):
        repository.resolve_unknown_step(
            workflow_id, 1, "failed", owner_user_id="user-b"
        )

def test_running_cancellation_persists_intent_until_worker_finalizes(tmp_path):
    repository = make_repository(tmp_path)
    TaskRepository(repository.database_path).create_auth_user(
        "owner-a", "owner-a", "salt", "hash"
    )
    task = TaskRecord(task_type="agent.workflow", description="cancel intent")
    workflow_id = repository.create_run(
        "a" * 64,
        [{"step_number": 1, "kind": "safe_tool", "name": "text.echo"}],
        task=task,
        owner_user_id="owner-a",
    )
    tasks = TaskRepository(repository.database_path)
    JobEngine(tasks).transition(task.task_id, TaskStatus.RUNNING)
    lease = LeaseManager(repository.database_path).acquire(
        str(task.task_id), "cancellation-test-worker"
    )
    assert lease is not None
    repository.start_run(workflow_id, lease=lease)

    result = repository.request_cancellation(
        workflow_id, owner_user_id="owner-a"
    )

    assert result["status"] == "cancellation_requested"
    stored_task = tasks.get(task.task_id)
    assert stored_task is not None and stored_task.status is TaskStatus.RUNNING
    with tasks._connection() as connection:
        row = connection.execute(
            "SELECT error_code FROM worker_executions WHERE task_id = ?",
            (str(task.task_id),),
        ).fetchone()
    assert row is not None and row["error_code"] == "cancellation_requested"
