from threading import Event, Thread

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


def test_stop_during_active_handler_drains_current_task_but_blocks_next_claim(tmp_path):
    repository = TaskRepository(tmp_path / "worker-control-inflight.sqlite3")
    repository.initialize()
    active = TaskRecord(task_type="demo.echo", description="already running")
    queued = TaskRecord(task_type="demo.echo", description="must remain queued")
    repository.create(active)
    repository.create(queued)

    control = WorkerControlRepository(repository.database_path)
    worker = WorkerEngine(repository)
    entered = Event()
    release = Event()
    calls = []

    def blocking_handler(task):
        calls.append(task.task_id)
        entered.set()
        assert release.wait(timeout=5)
        return {"message": task.description}

    worker.handlers["demo.echo"] = blocking_handler
    results = []
    thread = Thread(target=lambda: results.append(worker.run_once()))
    thread.start()
    assert entered.wait(timeout=3)

    stopped = control.set_stopped(
        True, reason="operator requested stop", changed_by="owner-1"
    )
    assert stopped["stopped"] is True
    release.set()
    thread.join(timeout=5)

    assert not thread.is_alive()
    assert len(results) == 1
    assert results[0] is not None and results[0].status is TaskStatus.SUCCEEDED
    assert calls == [active.task_id]

    # Stop is a dispatch-quiesce control, not a force-kill of in-flight Python code.
    assert worker.run_once() is None
    active_after = repository.get(active.task_id)
    queued_after = repository.get(queued.task_id)
    assert active_after is not None and active_after.status is TaskStatus.SUCCEEDED
    assert queued_after is not None and queued_after.status is TaskStatus.QUEUED
    assert calls == [active.task_id]
