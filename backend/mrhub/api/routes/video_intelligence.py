"""Authenticated video-intelligence prompt and brand-profile APIs."""

from __future__ import annotations

import sqlite3
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field, model_validator

from mrhub.api.dependencies import require_user
from mrhub.config import get_settings
from mrhub.media.repository import MediaAssetRepository
from mrhub.security.auth import AuthenticatedUser
from mrhub.video_intelligence.repository import VideoBrandRepository
from mrhub.video_intelligence.schemas import BeatInstruction, BrandIdentity
from mrhub.video_intelligence.service import build_generation_prompt

router = APIRouter(
    prefix="/video-intelligence",
    tags=["video-intelligence"],
    dependencies=[Depends(require_user)],
)


class PromptCompositionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    style_summary: str = Field(min_length=1, max_length=1000)
    beats: list[BeatInstruction] = Field(default_factory=list, max_length=20)
    duration_seconds: int = Field(default=10, ge=3, le=60)
    aspect_ratio: str = Field(default="9:16", pattern=r"^(9:16|16:9|1:1|4:5)$")
    brand_name: str | None = Field(default=None, max_length=80)
    colors: list[Annotated[str, Field(max_length=40)]] = Field(default_factory=list, max_length=8)
    typography: str | None = Field(default=None, max_length=240)
    sound_design: str | None = Field(default=None, max_length=500)
    final_frame: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def validate_timeline(self) -> "PromptCompositionRequest":
        if any(beat.end_seconds > self.duration_seconds for beat in self.beats):
            raise ValueError("Beat timeline cannot exceed the requested duration")
        return self


def _brands() -> VideoBrandRepository:
    return VideoBrandRepository(get_settings().database_path)


def _validate_logo(owner_user_id: str, brand: BrandIdentity) -> None:
    if brand.logo_asset_id is None:
        return
    try:
        asset_id = UUID(brand.logo_asset_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Invalid logo asset ID") from exc
    asset = MediaAssetRepository(get_settings().database_path).get(owner_user_id, asset_id)
    if asset is None or not str(asset["media_type"]).startswith("image/"):
        raise HTTPException(status_code=422, detail="Logo must reference an image owned by this user")


@router.post("/prompts/compose")
def compose_prompt(
    payload: PromptCompositionRequest,
    _user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> dict[str, str]:
    """Compose a provider-neutral prompt from reviewed analysis facts."""
    prompt = build_generation_prompt(**payload.model_dump())
    return {"prompt": prompt, "status": "composed", "execution": "not_started"}


@router.get("/brands")
def list_brands(
    user: Annotated[AuthenticatedUser, Depends(require_user)],
    limit: int = Query(default=50, ge=1, le=100),
) -> dict[str, object]:
    profiles = _brands().list(user.user_id, limit)
    return {"profiles": profiles, "count": len(profiles)}


@router.post("/brands", status_code=status.HTTP_201_CREATED)
def create_brand(
    payload: BrandIdentity,
    user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> dict[str, object]:
    _validate_logo(user.user_id, payload)
    try:
        return _brands().create(user.user_id, payload)
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=409, detail="A brand with this name already exists") from exc


@router.get("/brands/{profile_id}")
def get_brand(
    profile_id: UUID,
    user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> dict[str, object]:
    profile = _brands().get(user.user_id, profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Brand profile not found")
    return profile


@router.put("/brands/{profile_id}")
def update_brand(
    profile_id: UUID,
    payload: BrandIdentity,
    user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> dict[str, object]:
    _validate_logo(user.user_id, payload)
    try:
        profile = _brands().update(user.user_id, profile_id, payload)
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=409, detail="A brand with this name already exists") from exc
    if profile is None:
        raise HTTPException(status_code=404, detail="Brand profile not found")
    return profile


@router.delete("/brands/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_brand(
    profile_id: UUID,
    user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> None:
    if not _brands().delete(user.user_id, profile_id):
        raise HTTPException(status_code=404, detail="Brand profile not found")
