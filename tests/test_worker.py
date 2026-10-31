from mrhub.domain.tasks import RiskClass, TaskRecord, TaskStatus
from mrhub.infrastructure.database import TaskRepository
from mrhub.jobs.worker import WorkerEngine


def make_worker(tmp_path):
    repository = TaskRepository(tmp_path / "worker.sqlite3")
    repository.initialize()
    return repository, WorkerEngine(repository)


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
