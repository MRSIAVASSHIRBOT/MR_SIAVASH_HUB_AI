from datetime import UTC, datetime, timedelta

import pytest

from mrhub.domain.tasks import TaskRecord, TaskStatus
from mrhub.infrastructure.database import TaskRepository
from mrhub.jobs.retry_policy import (
    MAX_RETRY_ATTEMPTS,
    MAX_RETRY_DELAY_SECONDS,
    RetryPolicy,
)
from mrhub.jobs.worker import RetryableWorkerError, WorkerEngine, WorkerError


def make_worker(tmp_path, *, clock=None, retry_policies=None):
    repository = TaskRepository(tmp_path / "worker-retry-policy.sqlite3")
    repository.initialize()
    worker = WorkerEngine(
        repository,
        clock=clock,
        retry_policies=retry_policies,
    )
    return repository, worker


def test_retry_policy_uses_bounded_exponential_backoff():
    policy = RetryPolicy(
        max_attempts=4,
        base_delay_seconds=3,
        max_delay_seconds=15,
    )

    assert [policy.delay_seconds(attempt_number=n) for n in (1, 2, 3, 4, 8)] == [
        3, 6, 12, 15, 15
    ]


def test_retry_after_is_honored_but_cannot_exceed_policy_cap():
    policy = RetryPolicy(base_delay_seconds=5, max_delay_seconds=30)

    assert policy.delay_seconds(
        attempt_number=1, retry_after_seconds=12
    ) == 12
    assert policy.delay_seconds(
        attempt_number=2, retry_after_seconds=120
    ) == 30


@pytest.mark.parametrize(
    "kwargs",
    [
        {"retryable_error_codes": {"rate_limited"}},
        {"max_attempts": 0},
        {"base_delay_seconds": 0},
        {"base_delay_seconds": 10, "max_delay_seconds": 5},
        {"retryable_error_codes": frozenset()},
        {"retryable_error_codes": frozenset({"UPSTREAM_TIMEOUT"})},
    ],
)
def test_retry_policy_rejects_invalid_configuration(kwargs):
    with pytest.raises((TypeError, ValueError)):
        RetryPolicy(**kwargs)


@pytest.mark.parametrize(
    "retry_after",
    [-1, 86_401, True, 1.5],
)
def test_retryable_error_rejects_unbounded_retry_after(retry_after):
    with pytest.raises(ValueError):
        RetryableWorkerError(
            "transient", retry_after_seconds=retry_after
        )


def test_worker_honors_retry_after_for_an_allow_listed_idempotent_task(tmp_path):
    now = [datetime(2026, 11, 23, 10, 0, tzinfo=UTC)]
    policy = RetryPolicy(
        max_attempts=3,
        base_delay_seconds=5,
        max_delay_seconds=30,
        retryable_error_codes=frozenset({"rate_limited"}),
    )
    repository, worker = make_worker(
        tmp_path,
        clock=lambda: now[0],
        retry_policies={"demo.echo": policy},
    )
    task = TaskRecord(task_type="demo.echo", description="retry after")
    repository.create(task)
    worker.handlers["demo.echo"] = lambda _task: (_ for _ in ()).throw(
        RetryableWorkerError(
            "provider returned a transient rate limit",
            error_code="rate_limited",
            retry_after_seconds=120,
        )
    )

    scheduled = worker.run_once()

    assert scheduled is not None and scheduled.status is TaskStatus.QUEUED
    result = worker.get_result(task.task_id)
    assert result is not None
    assert result["next_attempt_at"] == (
        now[0] + timedelta(seconds=30)
    ).isoformat()


def test_worker_rejects_retry_error_codes_not_allowed_by_task_policy(tmp_path):
    policy = RetryPolicy(
        retryable_error_codes=frozenset({"rate_limited"})
    )
    repository, worker = make_worker(
        tmp_path,
        retry_policies={"demo.echo": policy},
    )
    task = TaskRecord(task_type="demo.echo", description="wrong retry class")
    repository.create(task)
    worker.handlers["demo.echo"] = lambda _task: (_ for _ in ()).throw(
        RetryableWorkerError("unexpected transient", error_code="upstream_timeout")
    )

    completed = worker.run_once()

    assert completed is not None and completed.status is TaskStatus.FAILED
    result = worker.get_result(task.task_id)
    assert result is not None and result["error_code"] == "retry_not_permitted"


def test_worker_cannot_configure_automatic_retries_for_external_task_types(tmp_path):
    repository = TaskRepository(tmp_path / "unsafe-retry-policy.sqlite3")
    repository.initialize()

    with pytest.raises(WorkerError, match="allow-listed idempotent"):
        WorkerEngine(
            repository,
            retry_policies={
                "video.generation": RetryPolicy(),
            },
        )



@pytest.mark.parametrize(
    ("kwargs", "field"),
    [
        ({"max_attempts": MAX_RETRY_ATTEMPTS + 1}, "max_attempts"),
        (
            {"base_delay_seconds": MAX_RETRY_DELAY_SECONDS + 1},
            "base_delay_seconds",
        ),
        (
            {"max_delay_seconds": MAX_RETRY_DELAY_SECONDS + 1},
            "max_delay_seconds",
        ),
    ],
)
def test_retry_policy_enforces_absolute_resource_bounds(kwargs, field):
    with pytest.raises(ValueError, match=field):
        RetryPolicy(**kwargs)


def test_retry_policy_accepts_the_documented_absolute_upper_bounds():
    policy = RetryPolicy(
        max_attempts=MAX_RETRY_ATTEMPTS,
        base_delay_seconds=MAX_RETRY_DELAY_SECONDS,
        max_delay_seconds=MAX_RETRY_DELAY_SECONDS,
    )

    assert policy.delay_seconds(attempt_number=MAX_RETRY_ATTEMPTS) == (
        MAX_RETRY_DELAY_SECONDS
    )
