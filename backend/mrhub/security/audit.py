"""Structured audit event recording with strict metadata allow-listing."""

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from mrhub.infrastructure.database import TaskRepository


class AuditEvent(BaseModel):
    """Minimal audit record; never contains credentials or arbitrary request bodies."""

    model_config = ConfigDict(frozen=True)

    event_id: str = Field(default_factory=lambda: str(uuid4()))
    event_type: str = Field(min_length=1, max_length=80)
    outcome: str = Field(min_length=1, max_length=40)
    subject_type: str = Field(default="task", max_length=40)
    subject_id: str | None = Field(default=None, max_length=80)
    actor_type: str = "system"
    actor_id: str | None = Field(default=None, max_length=80)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, str | int | bool | None] = Field(default_factory=dict)


class AuditLogger:
    """Records only explicitly approved, non-sensitive metadata fields."""

    ALLOWED_METADATA_KEYS = frozenset({
        "task_type",
        "risk_class",
        "previous_status",
        "new_status",
        "decision",
        "reason_code",
    })

    def __init__(self, repository: TaskRepository) -> None:
        self.repository = repository

    def record(
        self,
        event_type: str,
        outcome: str,
        subject_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        actor_type: str = "system",
        actor_id: str | None = None,
        subject_type: str = "task",
    ) -> AuditEvent:
        safe_metadata: dict[str, str | int | bool | None] = {}
        for key, value in (metadata or {}).items():
            if key not in self.ALLOWED_METADATA_KEYS:
                continue
            if value is None or isinstance(value, (str, int, bool)):
                safe_metadata[key] = value[:160] if isinstance(value, str) else value

        event = AuditEvent(
            event_type=event_type,
            outcome=outcome,
            subject_type=subject_type,
            subject_id=subject_id,
            actor_type=actor_type,
            actor_id=actor_id,
            metadata=safe_metadata,
        )
        self.repository.record_audit(event.model_dump(mode="json"))
        return event
