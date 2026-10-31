"""Task domain types."""

from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class TaskStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


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
