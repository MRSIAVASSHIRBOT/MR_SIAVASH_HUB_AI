"""Authenticated API for durable, approval-gated content scheduling."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from mrhub.api.dependencies import require_user
from mrhub.config import get_settings
from mrhub.content.scheduling import ContentScheduleRepository, ScheduleConflict
from mrhub.security.audit import AuditLogger
from mrhub.security.auth import AuthenticatedUser

router = APIRouter(
    prefix="/content", tags=["content-scheduling"], dependencies=[Depends(require_user)]
)
ScheduleStatus = Literal[
    "scheduled", "publishing", "published", "cancelled", "failed", "unknown_outcome"
]


class ScheduleCreate(BaseModel):
    scheduled_at: datetime


def _repository() -> ContentScheduleRepository:
    return ContentScheduleRepository(get_settings().database_path)


def _audit(
    repository: ContentScheduleRepository,
    user: AuthenticatedUser,
    event: str,
    schedule_id: str,
    reason: str,
) -> None:
    AuditLogger(repository.tasks).record(
        event_type=event,
        outcome="success",
        subject_type="content_publish_schedule",
        subject_id=schedule_id,
        actor_type="user",
        actor_id=user.user_id,
        metadata={"reason_code": reason},
    )


@router.post("/drafts/{draft_id}/schedule", status_code=201)
def schedule_draft(
    draft_id: UUID,
    payload: ScheduleCreate,
    user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> dict[str, object]:
    repository = _repository()
    try:
        record = repository.schedule(user.user_id, draft_id, payload.scheduled_at)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Content draft not found") from exc
    except ScheduleConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    _audit(
        repository, user, "content.schedule_created", str(record["schedule_id"]), "schedule_created"
    )
    return record


@router.get("/schedules")
def list_schedules(
    user: Annotated[AuthenticatedUser, Depends(require_user)],
    limit: int = Query(default=50, ge=1, le=100),
    status: ScheduleStatus | None = None,
) -> dict[str, object]:
    records = _repository().list_schedules(user.user_id, limit, status)
    return {"schedules": records, "count": len(records)}


@router.post("/schedules/{schedule_id}/cancel")
def cancel_schedule(
    schedule_id: UUID,
    user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> dict[str, object]:
    repository = _repository()
    try:
        record = repository.cancel(user.user_id, schedule_id)
    except ScheduleConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if record is None:
        raise HTTPException(status_code=404, detail="Schedule not found")
    _audit(repository, user, "content.schedule_cancelled", str(schedule_id), "schedule_cancelled")
    return record
