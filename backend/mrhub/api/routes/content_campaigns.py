"""Authenticated API for paired Instagram Reel and Telegram lesson campaigns."""
from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from mrhub.api.dependencies import require_user
from mrhub.config import get_settings
from mrhub.content.campaigns import CampaignConflict, ContentCampaignRepository
from mrhub.security.audit import AuditLogger
from mrhub.security.auth import AuthenticatedUser

router = APIRouter(
    prefix="/content/campaigns",
    tags=["content-campaigns"],
    dependencies=[Depends(require_user)],
)


class CampaignCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    instagram_draft_id: UUID
    telegram_draft_id: UUID


class CampaignSchedule(BaseModel):
    scheduled_at: datetime


def _repository() -> ContentCampaignRepository:
    return ContentCampaignRepository(get_settings().database_path)


def _audit(repository: ContentCampaignRepository, user: AuthenticatedUser,
           event: str, campaign_id: str, reason: str) -> None:
    AuditLogger(repository.tasks).record(
        event_type=event,
        outcome="success",
        subject_type="content_campaign",
        subject_id=campaign_id,
        actor_type="user",
        actor_id=user.user_id,
        metadata={"reason_code": reason},
    )


@router.get("")
def list_campaigns(
    user: Annotated[AuthenticatedUser, Depends(require_user)],
    limit: int = Query(default=50, ge=1, le=100),
) -> dict[str, object]:
    records = _repository().list(user.user_id, limit)
    return {"campaigns": records, "count": len(records)}


@router.post("", status_code=201)
def create_campaign(
    payload: CampaignCreate,
    user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> dict[str, object]:
    repository = _repository()
    try:
        record = repository.create(
            user.user_id, payload.title, payload.instagram_draft_id,
            payload.telegram_draft_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="One or both drafts were not found") from exc
    except CampaignConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    _audit(repository, user, "content.campaign_created",
           str(record["campaign_id"]), "campaign_created")
    return record


@router.get("/{campaign_id}")
def get_campaign(
    campaign_id: UUID,
    user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> dict[str, object]:
    record = _repository().get(user.user_id, campaign_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return record


@router.post("/{campaign_id}/schedule")
def schedule_campaign(
    campaign_id: UUID,
    payload: CampaignSchedule,
    user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> dict[str, object]:
    repository = _repository()
    try:
        record = repository.schedule(user.user_id, campaign_id, payload.scheduled_at)
    except CampaignConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if record is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    _audit(repository, user, "content.campaign_scheduled",
           str(campaign_id), "campaign_scheduled")
    return record
