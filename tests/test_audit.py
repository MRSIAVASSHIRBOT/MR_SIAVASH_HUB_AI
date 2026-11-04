from mrhub.infrastructure.database import TaskRepository
from mrhub.security.audit import AuditLogger


def test_audit_records_are_persisted_and_sensitive_keys_are_dropped(tmp_path) -> None:
    repository = TaskRepository(tmp_path / "audit.sqlite3")
    repository.initialize()
    logger = AuditLogger(repository)

    event = logger.record(
        event_type="task.submitted",
        outcome="queued",
        subject_id="task-123",
        metadata={
            "task_type": "demo.echo",
            "risk_class": "low",
            "api_key": "must-not-be-stored",
            "prompt": "private prompt text",
        },
    )

    assert event.metadata == {"task_type": "demo.echo", "risk_class": "low"}
    stored = repository.list_audit()
    assert len(stored) == 1
    assert stored[0]["event_type"] == "task.submitted"
    assert stored[0]["metadata"] == {"risk_class": "low", "task_type": "demo.echo"}
    assert "api_key" not in str(stored[0])
    assert "private prompt text" not in str(stored[0])


def test_agent_model_run_history_is_owner_scoped_and_bounded(tmp_path) -> None:
    repository = TaskRepository(tmp_path / "agent-model-history.sqlite3")
    repository.initialize()
    logger = AuditLogger(repository)

    logger.record(
        event_type="agent.model_run",
        outcome="success",
        subject_type="agent_run",
        subject_id="run-owner-a-1",
        actor_type="user",
        actor_id="owner-a",
        metadata={
            "provider_mode": "local",
            "status": "completed",
            "selected_provider": "test-local",
            "turns": 2,
            "tool_calls": 1,
            "context_passage_count": 3,
            "prompt": "must never be persisted",
        },
    )
    logger.record(
        event_type="agent.model_run",
        outcome="failure",
        subject_type="agent_run",
        subject_id="run-owner-b-1",
        actor_type="user",
        actor_id="owner-b",
        metadata={"provider_mode": "remote", "status": "provider_error"},
    )

    owner_a_runs = repository.list_agent_model_runs("owner-a", limit=1)
    assert len(owner_a_runs) == 1
    assert owner_a_runs[0]["run_id"] == "run-owner-a-1"
    assert owner_a_runs[0]["metadata"] == {
        "context_passage_count": 3,
        "provider_mode": "local",
        "selected_provider": "test-local",
        "status": "completed",
        "tool_calls": 1,
        "turns": 2,
    }
    assert repository.get_agent_model_run("owner-a", "run-owner-b-1") is None
    assert repository.get_agent_model_run("owner-b", "run-owner-b-1")["run_id"] == "run-owner-b-1"
