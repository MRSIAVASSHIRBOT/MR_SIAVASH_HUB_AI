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
