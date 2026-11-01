from concurrent.futures import ThreadPoolExecutor
from uuid import UUID

import pytest

from mrhub.infrastructure.database import TaskRepository
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
    repository.start_step(workflow_id, 1)

    assert repository.mark_interrupted(workflow_id) == 1
    run = repository.get_run(workflow_id)
    assert run is not None
    assert run["status"] == "recovery_required"
    assert run["steps"][0]["status"] == "unknown_outcome"

    decision = repository.resume_decision(workflow_id, "a" * 64)
    assert decision.decision == "reconcile"
    assert decision.reason_code == "worker_interrupted"
    with pytest.raises(RecoveryRequired):
        repository.start_step(workflow_id, 1)


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
