from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import pytest

from mrhub.domain.tasks import TaskRecord
from mrhub.infrastructure.database import TaskRepository
from mrhub.jobs.idempotency import (
    IdempotencyConflict,
    IdempotencyError,
    IdempotencyRepository,
)


def make_repository(tmp_path, clock=None):
    repository = TaskRepository(tmp_path / "idempotency.sqlite3")
    repository.initialize()
    return IdempotencyRepository(repository.database_path, clock=clock)


def test_reservation_is_created_once_and_same_request_is_deduplicated(tmp_path):
    repository = make_repository(tmp_path)
    first = repository.reserve("user:local", "request-1", "a" * 64)
    second = repository.reserve("user:local", "request-1", "a" * 64)

    assert first.created is True
    assert first.record.status == "accepted"
    assert second.created is False
    assert second.record == first.record


def test_reusing_key_for_different_request_is_a_conflict(tmp_path):
    repository = make_repository(tmp_path)
    repository.reserve("user:local", "request-2", "b" * 64)

    with pytest.raises(IdempotencyConflict):
        repository.reserve("user:local", "request-2", "c" * 64)


def test_same_key_is_independent_between_scopes(tmp_path):
    repository = make_repository(tmp_path)
    first = repository.reserve("user:a", "shared-key", "d" * 64)
    second = repository.reserve("user:b", "shared-key", "e" * 64)

    assert first.created is True
    assert second.created is True


def test_reservation_can_be_bound_to_a_task_once(tmp_path):
    repository = make_repository(tmp_path)
    reservation = repository.reserve("user:local", "request-3", "f" * 64)
    task_repository = TaskRepository(tmp_path / "idempotency.sqlite3")
    task = TaskRecord(task_type="agent.workflow", description="workflow task")
    task_repository.create(task)

    bound = repository.bind("user:local", "request-3", task_id=str(task.task_id))

    assert bound.task_id == str(task.task_id)
    assert reservation.record.task_id is None
    assert repository.reserve(
        "user:local", "request-3", "f" * 64, task_id=str(task.task_id)
    ).record.task_id == str(task.task_id)


def test_reservation_cannot_be_rebound_to_another_task(tmp_path):
    repository = make_repository(tmp_path)
    task_repository = TaskRepository(tmp_path / "idempotency.sqlite3")
    first_task = TaskRecord(task_type="agent.workflow")
    second_task = TaskRecord(task_type="agent.workflow")
    task_repository.create(first_task)
    task_repository.create(second_task)
    repository.reserve("user:local", "request-4", "1" * 64, task_id=str(first_task.task_id))

    with pytest.raises(IdempotencyConflict):
        repository.bind("user:local", "request-4", task_id=str(second_task.task_id))


def test_unknown_outcome_is_not_replayed_and_requires_reconciliation(tmp_path):
    repository = make_repository(tmp_path)
    repository.reserve("user:local", "request-5", "2" * 64)
    repository.transition("user:local", "request-5", "accepted", "running")
    unknown = repository.transition("user:local", "request-5", "running", "unknown_outcome")

    repeated = repository.reserve("user:local", "request-5", "2" * 64)
    assert repeated.created is False
    assert repeated.record.status == "unknown_outcome"
    assert unknown.status == "unknown_outcome"

    resolved = repository.resolve_unknown("user:local", "request-5", "completed")
    assert resolved.status == "completed"
    assert repository.reserve("user:local", "request-5", "2" * 64).created is False


def test_invalid_idempotency_transitions_are_rejected(tmp_path):
    repository = make_repository(tmp_path)
    repository.reserve("user:local", "request-6", "3" * 64)

    with pytest.raises(IdempotencyError):
        repository.transition("user:local", "request-6", "accepted", "completed")


def test_reservation_rejects_invalid_scope_key_and_digest(tmp_path):
    repository = make_repository(tmp_path)

    with pytest.raises(IdempotencyError):
        repository.reserve("", "key", "4" * 64)
    with pytest.raises(IdempotencyError):
        repository.reserve("scope", "", "4" * 64)
    with pytest.raises(IdempotencyError):
        repository.reserve("scope", "key", "not-a-digest")


def test_concurrent_identical_reservations_create_only_one_record(tmp_path):
    repository = make_repository(tmp_path)

    def reserve():
        return repository.reserve("user:local", "concurrent-key", "5" * 64)

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(lambda _index: reserve(), range(8)))

    assert sum(result.created for result in results) == 1
    assert {result.record.status for result in results} == {"accepted"}
    assert len({result.record.created_at for result in results}) == 1


def test_idempotency_clock_must_be_timezone_aware(tmp_path):
    repository = make_repository(tmp_path, clock=lambda: datetime(2026, 11, 1, 10, 0))

    with pytest.raises(IdempotencyError):
        repository.reserve("user:local", "naive-clock", "6" * 64)
