"""Authenticated video-intelligence prompt and brand-profile APIs."""

from __future__ import annotations

import sqlite3
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field, model_validator

from mrhub.api.dependencies import require_user
from mrhub.config import get_settings
from mrhub.infrastructure.database import TaskRepository
from mrhub.jobs.engine import InvalidTaskTransition, JobEngine
from mrhub.media.repository import MediaAssetRepository
from mrhub.security.audit import AuditLogger
from mrhub.security.auth import AuthenticatedUser
from mrhub.security.policy import ActionRequest, PolicyDecision, PolicyEngine
from mrhub.video_intelligence.repository import VideoBrandRepository
from mrhub.video_intelligence.scene_jobs import (
    SceneJobCapacityExceeded,
    SceneJobSourceNotFound,
    SceneJobSourceNotReady,
    SceneJobUnsupportedMedia,
    VideoSceneJobRepository,
)
from mrhub.video_intelligence.schemas import (
    BeatInstruction,
    BrandIdentity,
    VideoSceneAnalysisRequest,
    VideoTechnicalMetadata,
)
from mrhub.video_intelligence.service import build_generation_prompt, probe_video

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
    def validate_timeline(self) -> PromptCompositionRequest:
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



@router.get("/assets/{asset_id}/metadata", response_model=VideoTechnicalMetadata)
def inspect_video_asset(
    asset_id: UUID,
    user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> VideoTechnicalMetadata:
    """Probe technical metadata for a video asset owned by the authenticated user."""
    repository = MediaAssetRepository(get_settings().database_path)
    asset = repository.get(user.user_id, asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="Media asset not found")
    if asset["media_type"] not in {"video/mp4", "video/quicktime"}:
        raise HTTPException(status_code=415, detail="Asset is not a supported video")
    try:
        path = repository.file_path(str(asset["storage_key"]))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Media asset not found") from exc
    return probe_video(path)

@router.post("/assets/{asset_id}/scene-jobs", status_code=status.HTTP_202_ACCEPTED)
def submit_scene_job(
    asset_id: UUID,
    payload: VideoSceneAnalysisRequest,
    user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> dict[str, object]:
    """Queue bounded scene analysis for a video asset owned by the caller."""
    policy = PolicyEngine()
    risk_class = policy.classify_task_type("video.scene_detection")
    decision = policy.evaluate(
        ActionRequest(action="video.scene_detection", risk_class=risk_class)
    )
    if decision.decision is not PolicyDecision.ALLOW:
        raise HTTPException(status_code=403, detail="Scene analysis is not permitted")

    database_path = get_settings().database_path
    jobs = VideoSceneJobRepository(database_path)
    try:
        accepted = jobs.create(
            user.user_id,
            asset_id,
            threshold=payload.threshold,
            max_scene_changes=payload.max_scene_changes,
        )
    except SceneJobSourceNotFound as exc:
        raise HTTPException(status_code=404, detail="Media asset not found") from exc
    except SceneJobUnsupportedMedia as exc:
        raise HTTPException(status_code=415, detail="Scene analysis requires a video asset") from exc
    except SceneJobSourceNotReady as exc:
        raise HTTPException(status_code=409, detail="Media asset is not ready for analysis") from exc
    except SceneJobCapacityExceeded as exc:
        raise HTTPException(status_code=429, detail="Scene analysis capacity is temporarily full") from exc

    audit_repository = TaskRepository(database_path)
    AuditLogger(audit_repository).record(
        event_type="video.scene_job.submitted",
        outcome="queued",
        subject_type="video_scene_job",
        subject_id=str(accepted["job_id"]),
        actor_type="user",
        actor_id=user.user_id,
        metadata={"task_type": "video.scene_detection", "risk_class": risk_class.value},
    )
    return {
        **accepted,
        "message": "Scene analysis was added to the shared worker queue",
    }


@router.get("/scene-jobs/{job_id}")
def get_scene_job(
    job_id: UUID,
    user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> dict[str, object]:
    """Return queue state and sanitized results only to the job owner."""
    job = VideoSceneJobRepository(get_settings().database_path).get(
        user.user_id, job_id
    )
    if job is None:
        raise HTTPException(status_code=404, detail="Scene job not found")
    return job


@router.post("/scene-jobs/{job_id}/cancel")
def cancel_scene_job(
    job_id: UUID,
    user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> dict[str, object]:
    """Cancel a queued/running scene job after verifying ownership."""
    database_path = get_settings().database_path
    jobs = VideoSceneJobRepository(database_path)
    job = jobs.get(user.user_id, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Scene job not found")
    repository = TaskRepository(database_path)
    repository.initialize()
    try:
        JobEngine(repository).cancel(UUID(str(job["task_id"])))
    except InvalidTaskTransition as exc:
        raise HTTPException(status_code=409, detail="Scene job is already terminal") from exc
    updated = jobs.get(user.user_id, job_id)
    if updated is None:
        raise HTTPException(status_code=404, detail="Scene job not found")
    return updated

