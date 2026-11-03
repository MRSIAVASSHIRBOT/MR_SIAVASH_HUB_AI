import sqlite3
from threading import Event

import pytest

from mrhub.infrastructure.database import TaskRepository
from mrhub.jobs.leases import LeaseError, WorkerLease
from mrhub.agents.workflow_runner import AgentWorkflowRunner


@pytest.mark.parametrize(
    "heartbeat_error",
    [
        sqlite3.OperationalError("database is locked"),
        LeaseError("lease clock is invalid"),
    ],
)
def test_local_workflow_runner_fails_closed_when_heartbeat_raises(
    tmp_path, monkeypatch, heartbeat_error
):
    repository = TaskRepository(tmp_path / "workflow-runner.sqlite3")
    repository.initialize()
    runner = AgentWorkflowRunner(repository, core=None, lease_seconds=1)
    lease = WorkerLease(
        task_id="task-1",
        owner="worker-1",
        fencing_token=1,
        expires_at="2026-11-03T00:01:00+00:00",
    )
    lease_lost = Event()

    class FailingLeaseManager:
        def heartbeat(self, _lease):
            raise heartbeat_error

    monkeypatch.setattr(runner, "lease_manager", FailingLeaseManager())
    runner._heartbeat_loop(lease, Event(), lease_lost)

    assert lease_lost.is_set()
