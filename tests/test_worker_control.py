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



def test_emergency_stop_does_not_replay_inflight_handler_and_blocks_next_claim(tmp_path):
    from threading import Event, Thread

    repository = TaskRepository(tmp_path / "worker-control-inflight.sqlite3")
    repository.initialize()
    first_task = TaskRecord(task_type="demo.echo", description="in-flight")
    second_task = TaskRecord(task_type="demo.echo", description="must remain queued")
    repository.create(first_task)
    repository.create(second_task)

    control = WorkerControlRepository(repository.database_path)
    worker = WorkerEngine(repository, lease_seconds=3)
    entered = Event()
    release = Event()
    calls = []

    def in_flight_handler(task):
        calls.append(str(task.task_id))
        entered.set()
        assert release.wait(timeout=3)
        return {"message": "completed once"}

    worker.handlers["demo.echo"] = in_flight_handler
    result = []
    thread = Thread(target=lambda: result.append(worker.run_once()))
    thread.start()
    assert entered.wait(timeout=2)

    stopped = control.set_stopped(
        True, reason="stop during in-flight operation", changed_by="operator"
    )
    assert stopped["stopped"] is True

    # Emergency stop is a dispatch gate, not a claim that an already-running
    # synchronous handler has been cancelled or its external effect rolled back.
    second_worker = WorkerEngine(repository, lease_seconds=3)
    assert second_worker.run_once() is None
    queued = repository.get(second_task.task_id)
    assert queued is not None and queued.status is TaskStatus.QUEUED

    release.set()
    thread.join(timeout=4)
    assert not thread.is_alive()
    assert len(calls) == 1
    assert result[0] is not None and result[0].status is TaskStatus.SUCCEEDED
    completed = repository.get(first_task.task_id)
    assert completed is not None and completed.status is TaskStatus.SUCCEEDED

    # A stop must remain latched until an explicit operator resume.
    assert second_worker.run_once() is None
    assert calls == [str(first_task.task_id)]

    control.set_stopped(False, reason=None, changed_by="operator")
    second_worker.handlers["demo.echo"] = lambda task: {"message": task.description}
    resumed = second_worker.run_once()
    assert resumed is not None and resumed.task_id == second_task.task_id
    assert resumed.status is TaskStatus.SUCCEEDED
