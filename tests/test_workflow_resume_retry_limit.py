"""Regression tests for bounded safe workflow recovery attempts."""

import pytest

from mrhub.domain.tasks import TaskRecord, TaskStatus
from mrhub.infrastructure.database import TaskRepository
from mrhub.jobs.engine import JobEngine
from mrhub.jobs.leases import LeaseManager
from mrhub.jobs.recovery import (
    WorkflowRecoveryError,
    WorkflowRecoveryRepository,
)


def test_safe_workflow_step_cannot_be_resumed_after_attempt_limit(tmp_path) -> None:
    tasks = TaskRepository(tmp_path / "workflow-retry-limit.sqlite3")
    tasks.initialize()
    recovery = WorkflowRecoveryRepository(tasks.database_path)
    jobs = JobEngine(tasks)
    lease_manager = LeaseManager(tasks.database_path, lease_seconds=60)

    task = TaskRecord(task_type="agent.workflow", description="bounded recovery test")
    request_digest = "a" * 64
    workflow_id = recovery.create_run(
        request_digest,
        [
            {
                "step_number": 1,
                "kind": "provider_selection",
                "name": "provider_selection",
                "step_key": "step-1",
                "depends_on": [],
            },
            {
                "step_number": 2,
                "kind": "safe_tool",
                "name": "text.echo",
                "step_key": "echo",
                "depends_on": ["step-1"],
                "input_digest": "b" * 64,
            },
        ],
        task=task,
        definition_version=3,
        owner_user_id="retry-test-owner",
    )

    jobs.transition(task.task_id, TaskStatus.RUNNING)
    lease = lease_manager.acquire(str(task.task_id), "retry-limit-test-worker")
    assert lease is not None

    recovery.start_run(workflow_id, lease=lease)
    provider_attempt = recovery.start_step(workflow_id, "step-1", lease=lease)
    recovery.complete_step(
        workflow_id, provider_attempt, "c" * 64, lease=lease
    )

    # Simulate repeated worker crashes while the same safe step is running.
    for attempt_number in range(1, recovery.MAX_SAFE_STEP_ATTEMPTS + 1):
        if attempt_number > 1:
            recovery.start_run(workflow_id, lease=lease)
        attempt = recovery.start_step(workflow_id, "echo", lease=lease)
        assert attempt.attempt_number == attempt_number
        recovery.mark_interrupted(workflow_id, lease=lease)

    # Worker recovery moves the durable task to its owner-review state.
    jobs.transition(task.task_id, TaskStatus.WAITING_APPROVAL, lease=lease)

    with pytest.raises(WorkflowRecoveryError, match="retry limit exceeded"):
        recovery.queue_resume(
            workflow_id,
            owner_user_id="retry-test-owner",
            request_digest=request_digest,
            definition_version=3,
        )

    run = recovery.get_run(workflow_id, owner_user_id="retry-test-owner")
    saved_task = tasks.get(task.task_id)
    assert run is not None and run["status"] == "failed"
    assert saved_task is not None and saved_task.status is TaskStatus.FAILED

    with tasks._connection() as connection:
        step = connection.execute(
            """
            SELECT status, attempt_count, error_code
            FROM workflow_steps
            WHERE workflow_id = ? AND step_key = 'echo'
            """,
            (str(workflow_id),),
        ).fetchone()
        execution = connection.execute(
            """
            SELECT error_code, next_attempt_at
            FROM worker_executions WHERE task_id = ?
            """,
            (str(task.task_id),),
        ).fetchone()

    assert step is not None
    assert step["status"] == "failed"
    assert step["attempt_count"] == recovery.MAX_SAFE_STEP_ATTEMPTS
    assert step["error_code"] == "retry_limit_exceeded"
    assert execution is not None
    assert execution["error_code"] == "step_retry_limit_exceeded"
    assert execution["next_attempt_at"] is None

    lease_manager.release(lease)

def test_safe_step_cannot_bypass_attempt_limit_with_direct_start(tmp_path) -> None:
    tasks = TaskRepository(tmp_path / "direct-step-retry-limit.sqlite3")
    tasks.initialize()
    recovery = WorkflowRecoveryRepository(tasks.database_path)
    jobs = JobEngine(tasks)
    lease_manager = LeaseManager(tasks.database_path, lease_seconds=60)

    task = TaskRecord(
        task_type="agent.workflow",
        description="direct retry guard test",
    )
    workflow_id = recovery.create_run(
        "d" * 64,
        [
            {
                "step_number": 1,
                "kind": "safe_tool",
                "name": "text.echo",
                "step_key": "echo",
                "depends_on": [],
                "input_digest": "e" * 64,
            }
        ],
        task=task,
        definition_version=1,
        owner_user_id="direct-retry-test-owner",
    )

    jobs.transition(task.task_id, TaskStatus.RUNNING)
    lease = lease_manager.acquire(str(task.task_id), "direct-retry-test-worker")
    assert lease is not None
    recovery.start_run(workflow_id, lease=lease)

    with tasks._connection() as connection:
        connection.execute(
            """
            UPDATE workflow_steps
            SET status = 'retry_wait', attempt_count = ?
            WHERE workflow_id = ? AND step_key = 'echo'
            """,
            (recovery.MAX_SAFE_STEP_ATTEMPTS, str(workflow_id)),
        )

    with pytest.raises(WorkflowRecoveryError, match="retry limit exceeded"):
        recovery.start_step(workflow_id, "echo", lease=lease)

    with tasks._connection() as connection:
        step = connection.execute(
            """
            SELECT status, attempt_count
            FROM workflow_steps WHERE workflow_id = ? AND step_key = 'echo'
            """,
            (str(workflow_id),),
        ).fetchone()

    assert step is not None
    assert step["status"] == "retry_wait"
    assert step["attempt_count"] == recovery.MAX_SAFE_STEP_ATTEMPTS
    lease_manager.release(lease)
