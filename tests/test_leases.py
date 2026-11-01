from datetime import UTC, datetime, timedelta

from mrhub.domain.tasks import TaskRecord, TaskStatus
from mrhub.infrastructure.database import TaskRepository
from mrhub.jobs.leases import LeaseManager


def make_running_task(tmp_path):
    repository = TaskRepository(tmp_path / "leases.sqlite3")
    repository.initialize()
    task = TaskRecord(task_type="demo.echo", description="lease test")
    repository.create(task)
    with repository._connection() as connection:
        connection.execute(
            "UPDATE tasks SET status = ? WHERE task_id = ?",
            (TaskStatus.RUNNING.value, str(task.task_id)),
        )
        connection.execute(
            "INSERT INTO worker_executions (task_id, attempt_count, started_at) "
            "VALUES (?, 1, ?)",
            (str(task.task_id), datetime.now(UTC).isoformat()),
        )
    return repository, task


def test_only_one_worker_can_hold_an_unexpired_lease(tmp_path):
    repository, task = make_running_task(tmp_path)
    first = LeaseManager(repository.database_path)
    second = LeaseManager(repository.database_path)

    lease = first.acquire(str(task.task_id), "worker-a")

    assert lease is not None
    assert lease.fencing_token == 1
    assert first.is_current(lease)
    assert second.acquire(str(task.task_id), "worker-b") is None


def test_expired_lease_can_be_taken_over_with_a_higher_fencing_token(tmp_path):
    repository, task = make_running_task(tmp_path)
    now = [datetime(2026, 11, 1, 10, 0, tzinfo=UTC)]
    manager = LeaseManager(
        repository.database_path,
        lease_seconds=30,
        clock=lambda: now[0],
    )

    first = manager.acquire(str(task.task_id), "worker-a")
    assert first is not None
    now[0] += timedelta(seconds=31)
    assert not manager.is_current(first)

    second = manager.acquire(str(task.task_id), "worker-b")

    assert second is not None
    assert second.fencing_token == first.fencing_token + 1
    assert second.owner == "worker-b"
    assert not manager.is_current(first)
    assert manager.is_current(second)


def test_heartbeat_renews_only_the_current_lease(tmp_path):
    repository, task = make_running_task(tmp_path)
    now = [datetime(2026, 11, 1, 10, 0, tzinfo=UTC)]
    manager = LeaseManager(
        repository.database_path,
        lease_seconds=30,
        clock=lambda: now[0],
    )
    lease = manager.acquire(str(task.task_id), "worker-a")
    assert lease is not None

    now[0] += timedelta(seconds=20)
    renewed = manager.heartbeat(lease)

    assert renewed is not None
    assert renewed.fencing_token == lease.fencing_token
    assert renewed.expires_at > lease.expires_at
    assert manager.is_current(renewed)


def test_stale_owner_cannot_heartbeat_or_release_after_takeover(tmp_path):
    repository, task = make_running_task(tmp_path)
    now = [datetime(2026, 11, 1, 10, 0, tzinfo=UTC)]
    manager = LeaseManager(
        repository.database_path,
        lease_seconds=10,
        clock=lambda: now[0],
    )
    first = manager.acquire(str(task.task_id), "worker-a")
    assert first is not None

    now[0] += timedelta(seconds=11)
    second = manager.acquire(str(task.task_id), "worker-b")
    assert second is not None

    assert manager.heartbeat(first) is None
    assert not manager.release(first)
    assert manager.is_current(second)


def test_release_is_bound_to_owner_and_fencing_token(tmp_path):
    repository, task = make_running_task(tmp_path)
    manager = LeaseManager(repository.database_path)
    lease = manager.acquire(str(task.task_id), "worker-a")
    assert lease is not None

    wrong_owner = lease.__class__(
        task_id=lease.task_id,
        owner="worker-b",
        fencing_token=lease.fencing_token,
        expires_at=lease.expires_at,
    )
    assert not manager.release(wrong_owner)
    assert manager.release(lease)
    assert not manager.is_current(lease)


def test_lease_is_not_granted_for_non_running_tasks(tmp_path):
    repository = TaskRepository(tmp_path / "queued.sqlite3")
    repository.initialize()
    task = TaskRecord(task_type="demo.echo", description="not claimed")
    repository.create(task)
    with repository._connection() as connection:
        connection.execute(
            "INSERT INTO worker_executions (task_id, attempt_count) VALUES (?, 0)",
            (str(task.task_id),),
        )

    manager = LeaseManager(repository.database_path)
    assert manager.acquire(str(task.task_id), "worker-a") is None
