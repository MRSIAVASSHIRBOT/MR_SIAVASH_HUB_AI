"""Task domain types."""

from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


class TaskStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


class TaskPriority(StrEnum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class RiskClass(StrEnum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    PROHIBITED = "prohibited"


class TaskRecord(BaseModel):
    """Persistable task metadata. Task input is intentionally not executable."""

    model_config = ConfigDict(frozen=True)

    task_id: UUID = Field(default_factory=uuid4)
    task_type: str = Field(min_length=1, max_length=80)
    status: TaskStatus = TaskStatus.QUEUED
    risk_class: RiskClass = RiskClass.LOW
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    description: str = Field(default="", max_length=500)
    priority: TaskPriority = TaskPriority.NORMAL
    deadline_at: datetime | None = None

    @field_validator("deadline_at")
    @classmethod
    def normalize_deadline(cls, value: datetime | None) -> datetime | None:
        """Require an explicit timezone and normalize persisted deadlines to UTC."""
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("deadline_at must include a timezone")
        return value.astimezone(UTC)
