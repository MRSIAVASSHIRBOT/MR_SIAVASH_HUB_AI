from mrhub.domain.tasks import TaskRecord, TaskStatus
from mrhub.infrastructure.database import TaskRepository
from mrhub.jobs.worker import WorkerEngine
from mrhub.jobs.worker_control import WorkerControlRepository


def test_emergency_stop_persists_and_prevents_new_task_claims(tmp_path):
    repository = TaskRepository(tmp_path / "worker-control.sqlite3")
    repository.initialize()
    task = TaskRecord(task_type="demo.echo", description="must wait")
    repository.create(task)
    control = WorkerControlRepository(repository.database_path)

    stopped = control.set_stopped(
        True, reason="operator requested stop", changed_by="owner-1"
    )
    assert stopped["stopped"] is True
    assert stopped["reason"] == "operator requested stop"

    # A new worker instance reads the persisted stop state, not process-local memory.
    worker = WorkerEngine(repository)
    assert worker.run_once() is None
    queued = repository.get(task.task_id)
    assert queued is not None and queued.status is TaskStatus.QUEUED

    resumed = control.set_stopped(False, reason=None, changed_by="owner-1")
    assert resumed["stopped"] is False
    completed = worker.run_once()
    assert completed is not None and completed.status is TaskStatus.SUCCEEDED


def test_worker_control_defaults_to_running_after_schema_migration(tmp_path):
    repository = TaskRepository(tmp_path / "worker-control-default.sqlite3")
    repository.initialize()
    state = WorkerControlRepository(repository.database_path).get()

    assert state["stopped"] is False
    assert state["reason"] is None
