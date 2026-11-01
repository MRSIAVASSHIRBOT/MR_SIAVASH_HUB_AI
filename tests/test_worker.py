from datetime import UTC, datetime, timedelta

from mrhub.domain.tasks import RiskClass, TaskRecord, TaskStatus
from mrhub.infrastructure.database import TaskRepository
from mrhub.jobs.engine import JobEngine
from mrhub.jobs.worker import RetryableWorkerError, WorkerEngine


def make_worker(tmp_path, clock=None):
    repository = TaskRepository(tmp_path / "worker.sqlite3")
    repository.initialize()
    return repository, WorkerEngine(repository, clock=clock)


def test_worker_executes_only_registered_echo_handler(tmp_path):
    repository, worker = make_worker(tmp_path)
    task = TaskRecord(task_type="demo.echo", description="hello worker")
    repository.create(task)

    completed = worker.run_once()

    assert completed is not None
    assert completed.task_id == task.task_id
    assert completed.status is TaskStatus.SUCCEEDED
    stored = repository.get(task.task_id)
    assert stored is not None and stored.status is TaskStatus.SUCCEEDED
    result = worker.get_result(task.task_id)
    assert result is not None
    assert result["result"] == {"message": "hello worker", "task_type": "demo.echo"}
    assert result["attempt_count"] == 1


def test_worker_fails_closed_for_unregistered_task_type(tmp_path):
    repository, worker = make_worker(tmp_path)
    task = TaskRecord(task_type="unknown.operation", description="not executable")
    repository.create(task)

    completed = worker.run_once()

    assert completed is not None and completed.status is TaskStatus.FAILED
    result = worker.get_result(task.task_id)
    assert result is not None and result["error_code"] == "handler_not_registered"


def test_high_risk_task_requires_matching_approval_fingerprint(tmp_path):
    repository, worker = make_worker(tmp_path)
    task = TaskRecord(
        task_type="external.publish",
        description="publish reviewed content",
        risk_class=RiskClass.HIGH,
    )
    repository.create(task)

    completed = worker.run_once()

    assert completed is not None and completed.status is TaskStatus.FAILED
    result = worker.get_result(task.task_id)
    assert result is not None
    assert result["error_code"] == "approval_missing_or_stale"


def test_high_risk_task_fingerprint_is_checked_before_handler_lookup(tmp_path):
    repository, worker = make_worker(tmp_path)
    repository.create_auth_user("local-owner", "owner", "salt", "hash")
    task = TaskRecord(
        task_type="external.publish",
        description="publish reviewed content",
        risk_class=RiskClass.HIGH,
    )
    repository.create(task)
    repository.record_task_approval(
        {
            "approval_id": "approval-1",
            "task_id": str(task.task_id),
            "decision": "approved",
            "approver_id": "local-owner",
            "action_fingerprint": "0" * 64,
            "reason": "test",
            "created_at": task.created_at.isoformat(),
        },
        expected_status=TaskStatus.QUEUED,
        target_status=TaskStatus.QUEUED,
    )

    completed = worker.run_once()

    assert completed is not None and completed.status is TaskStatus.FAILED
    result = worker.get_result(task.task_id)
    assert result is not None
    assert result["error_code"] == "approval_missing_or_stale"


def test_worker_returns_none_for_empty_queue(tmp_path):
    _repository, worker = make_worker(tmp_path)
    assert worker.run_once() is None


def test_stale_running_task_is_recovered_as_failed_not_replayed(tmp_path):
    repository, worker = make_worker(tmp_path)
    task = TaskRecord(task_type="demo.echo", description="interrupted")
    repository.create(task)
    with repository._connection() as connection:
        connection.execute(
            "UPDATE tasks SET status = ? WHERE task_id = ?",
            (TaskStatus.RUNNING.value, str(task.task_id)),
        )
        connection.execute(
            """
            INSERT INTO worker_executions (task_id, attempt_count, started_at)
            VALUES (?, 1, ?)
            """,
            (str(task.task_id), "2000-01-01T00:00:00+00:00"),
        )

    assert worker.run_once() is None
    stored = repository.get(task.task_id)
    assert stored is not None and stored.status is TaskStatus.FAILED
    result = worker.get_result(task.task_id)
    assert result is not None
    assert result["error_code"] == "worker_interrupted"
    assert result["recovered_at"] is not None


def test_worker_does_not_overwrite_cancellation_after_handler_returns(tmp_path):
    repository, worker = make_worker(tmp_path)
    task = TaskRecord(task_type="demo.echo", description="cancel during handler")
    repository.create(task)

    def cancel_then_return(current_task):
        JobEngine(repository).cancel(current_task.task_id)
        return {"message": "handler returned"}

    worker.handlers["demo.echo"] = cancel_then_return
    completed = worker.run_once()

    assert completed is not None and completed.status is TaskStatus.CANCELLED
    stored = repository.get(task.task_id)
    assert stored is not None and stored.status is TaskStatus.CANCELLED
    result = worker.get_result(task.task_id)
    assert result is not None
    assert result["result"] is None
    assert result["error_code"] == "cancelled_during_execution"


def test_retryable_echo_error_is_scheduled_with_exponential_backoff(tmp_path):
    now = [datetime(2026, 11, 1, 10, 0, tzinfo=UTC)]
    repository, worker = make_worker(tmp_path, clock=lambda: now[0])
    task = TaskRecord(task_type="demo.echo", description="retry me")
    repository.create(task)
    calls = []

    def transient_then_success(current_task):
        calls.append(current_task.task_id)
        if len(calls) == 1:
            raise RetryableWorkerError("temporary condition")
        return {"message": "recovered"}

    worker.handlers["demo.echo"] = transient_then_success

    first = worker.run_once()
    assert first is not None and first.status is TaskStatus.QUEUED
    result = worker.get_result(task.task_id)
    assert result is not None
    assert result["attempt_count"] == 1
    assert result["error_code"] == "retry_scheduled"
    assert result["next_attempt_at"] == (now[0] + timedelta(seconds=5)).isoformat()

    assert worker.run_once() is None
    now[0] += timedelta(seconds=5)
    second = worker.run_once()
    assert second is not None and second.status is TaskStatus.SUCCEEDED
    assert worker.get_result(task.task_id)["attempt_count"] == 2


def test_retry_limit_fails_after_three_attempts(tmp_path):
    now = [datetime(2026, 11, 1, 10, 0, tzinfo=UTC)]
    repository, worker = make_worker(tmp_path, clock=lambda: now[0])
    task = TaskRecord(task_type="demo.echo", description="always transient")
    repository.create(task)
    worker.handlers["demo.echo"] = lambda _task: (_ for _ in ()).throw(
        RetryableWorkerError("temporary")
    )

    for delay in (0, 5, 10):
        now[0] += timedelta(seconds=delay)
        completed = worker.run_once()

    assert completed is not None and completed.status is TaskStatus.FAILED
    result = worker.get_result(task.task_id)
    assert result is not None
    assert result["attempt_count"] == 3
    assert result["error_code"] == "retry_limit_exceeded"


def test_retry_is_not_permitted_for_unregistered_task_types(tmp_path):
    repository, worker = make_worker(tmp_path)
    task = TaskRecord(task_type="unknown.operation", description="not retryable")
    repository.create(task)
    # Simulate a future handler accidentally being registered without retry policy.
    worker.handlers[task.task_type] = lambda _task: (_ for _ in ()).throw(
        RetryableWorkerError("temporary")
    )

    completed = worker.run_once()

    assert completed is not None and completed.status is TaskStatus.FAILED
    result = worker.get_result(task.task_id)
    assert result is not None and result["error_code"] == "retry_not_permitted"


def test_retry_schedule_survives_worker_recreation(tmp_path):
    now = [datetime(2026, 11, 1, 10, 0, tzinfo=UTC)]
    repository, worker = make_worker(tmp_path, clock=lambda: now[0])
    task = TaskRecord(task_type="demo.echo", description="persist schedule")
    repository.create(task)
    worker.handlers["demo.echo"] = lambda _task: (_ for _ in ()).throw(
        RetryableWorkerError("temporary")
    )

    scheduled = worker.run_once()
    assert scheduled is not None and scheduled.status is TaskStatus.QUEUED

    recreated = WorkerEngine(repository, clock=lambda: now[0])
    assert recreated.run_once() is None
    now[0] += timedelta(seconds=5)
    recreated.handlers["demo.echo"] = lambda _task: {"message": "done"}
    completed = recreated.run_once()
    assert completed is not None and completed.status is TaskStatus.SUCCEEDED


def test_two_worker_instances_do_not_execute_the_same_task_concurrently(tmp_path):
    from threading import Event, Thread

    repository = TaskRepository(tmp_path / "shared.sqlite3")
    repository.initialize()
    first = WorkerEngine(repository, lease_seconds=3)
    second = WorkerEngine(repository, lease_seconds=3)
    task = TaskRecord(task_type="demo.echo", description="one execution")
    repository.create(task)
    entered = Event()
    release = Event()
    calls = []

    def blocked_handler(current_task):
        calls.append(current_task.task_id)
        entered.set()
        assert release.wait(timeout=3)
        return {"message": current_task.description}

    first.handlers["demo.echo"] = blocked_handler
    thread_result = []
    thread = Thread(target=lambda: thread_result.append(first.run_once()))
    thread.start()
    assert entered.wait(timeout=2)

    assert second.run_once() is None
    release.set()
    thread.join(timeout=3)

    assert not thread.is_alive()
    assert len(calls) == 1
    assert thread_result[0] is not None
    assert thread_result[0].status is TaskStatus.SUCCEEDED


def test_worker_heartbeat_keeps_long_running_handler_lease_alive(tmp_path):
    from threading import Event, Thread
    from time import sleep

    repository = TaskRepository(tmp_path / "heartbeat.sqlite3")
    repository.initialize()
    worker = WorkerEngine(repository, lease_seconds=1)
    task = TaskRecord(task_type="demo.echo", description="heartbeat")
    repository.create(task)
    entered = Event()
    release = Event()

    def slow_handler(current_task):
        entered.set()
        assert release.wait(timeout=4)
        return {"message": current_task.description}

    worker.handlers["demo.echo"] = slow_handler
    result = []
    thread = Thread(target=lambda: result.append(worker.run_once()))
    thread.start()
    assert entered.wait(timeout=2)
    sleep(1.3)

    with repository._connection() as connection:
        row = connection.execute(
            "SELECT heartbeat_at, lease_expires_at FROM worker_executions WHERE task_id = ?",
            (str(task.task_id),),
        ).fetchone()
    assert row is not None and row["heartbeat_at"] is not None
    assert row["lease_expires_at"] is not None

    release.set()
    thread.join(timeout=3)
    assert not thread.is_alive()
    assert result[0] is not None and result[0].status is TaskStatus.SUCCEEDED


def test_worker_with_lost_fencing_token_cannot_commit_result(tmp_path):
    from threading import Event, Thread

    from mrhub.jobs.leases import LeaseManager

    repository = TaskRepository(tmp_path / "fencing.sqlite3")
    repository.initialize()
    worker = WorkerEngine(repository, lease_seconds=2)
    task = TaskRecord(task_type="demo.echo", description="stale worker")
    repository.create(task)
    entered = Event()
    release = Event()

    def delayed_handler(current_task):
        entered.set()
        assert release.wait(timeout=3)
        return {"message": "must not be committed"}

    worker.handlers["demo.echo"] = delayed_handler
    result = []
    thread = Thread(target=lambda: result.append(worker.run_once()))
    thread.start()
    assert entered.wait(timeout=2)

    with repository._connection() as connection:
        connection.execute(
            "UPDATE worker_executions SET lease_expires_at = ? WHERE task_id = ?",
            ("2000-01-01T00:00:00+00:00", str(task.task_id)),
        )

    successor = LeaseManager(repository.database_path).acquire(
        str(task.task_id), "successor-worker"
    )
    assert successor is not None
    release.set()
    thread.join(timeout=3)

    assert not thread.is_alive()
    stored = repository.get(task.task_id)
    assert stored is not None and stored.status is TaskStatus.RUNNING
    persisted = worker.get_result(task.task_id)
    assert persisted is not None and persisted["result"] is None
    assert LeaseManager(repository.database_path).is_current(successor)
