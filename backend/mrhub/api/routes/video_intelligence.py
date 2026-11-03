"""Authenticated video-intelligence prompt and brand-profile APIs."""

from __future__ import annotations

import sqlite3
from typing import Annotated, Literal
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    Header,
    HTTPException,
    Query,
    Response,
    status,
)
from pydantic import BaseModel, ConfigDict, Field, model_validator

from mrhub.api.dependencies import require_user
from mrhub.config import get_settings
from mrhub.jobs.payload_envelope import PayloadEnvelopeError
from mrhub.media.repository import MediaAssetRepository
from mrhub.security.auth import AuthenticatedUser
from mrhub.video_intelligence.jobs import (
    VideoAnalysisCapacityExceeded,
    VideoAnalysisConflict,
    VideoAnalysisJobRepository,
)
from mrhub.video_intelligence.prompt_from_analysis import (
    AnalysisPromptOptions,
    PromptCompositionUnavailable,
    compose_prompts_from_analysis,
)
from mrhub.video_intelligence.repository import VideoBrandRepository
from mrhub.video_intelligence.schemas import (
    BeatInstruction,
    BrandIdentity,
    VideoAnalysisRequest,
    VideoTechnicalMetadata,
)
from mrhub.video_intelligence.timeline_drafts import (
    TimelineBeat,
    TimelineConflict,
    TimelineDraftUpdate,
    VideoTimelineDraftRepository,
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


@router.get("/generation/providers")
def list_video_generation_providers(
    _user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> dict[str, object]:
    """Return configured generation adapters without probing or starting work."""
    # Intentionally empty until an adapter is explicitly configured and reviewed.
    from mrhub.video_intelligence.generation_registry import video_generation_registry

    providers = [item.model_dump(mode="json") for item in video_generation_registry.catalog()]
    return {
        "providers": providers,
        "count": len(providers),
        "generation_available": bool(providers),
        "reason_code": None if providers else "provider_unavailable",
        "execution": "not_started",
    }


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




def _timeline_drafts() -> VideoTimelineDraftRepository:
    return VideoTimelineDraftRepository(get_settings().database_path)

def _analysis_jobs() -> VideoAnalysisJobRepository:
    return VideoAnalysisJobRepository(get_settings().database_path)


@router.post("/analyses", status_code=status.HTTP_202_ACCEPTED)
def submit_video_analysis(
    payload: VideoAnalysisRequest,
    response: Response,
    user: Annotated[AuthenticatedUser, Depends(require_user)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> dict[str, object]:
    """Queue bounded analysis for video assets owned by the authenticated user."""
    if payload.brand is not None:
        # Inline logos must use the same owner-scoped image validation as saved profiles.
        _validate_logo(user.user_id, payload.brand)
    media = MediaAssetRepository(get_settings().database_path)
    for asset_value in payload.source_asset_ids:
        try:
            asset_id = UUID(asset_value)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="Invalid source asset ID") from exc
        asset = media.get(user.user_id, asset_id)
        if asset is None:
            raise HTTPException(status_code=404, detail="Video asset not found")
        if asset["media_type"] not in {"video/mp4", "video/quicktime"}:
            raise HTTPException(status_code=415, detail="Source asset is not a supported video")
        if asset["processing_status"] not in {"stored", "processed"}:
            raise HTTPException(status_code=409, detail="Source asset is not ready for analysis")

    try:
        accepted, created = _analysis_jobs().submit(
            user.user_id, payload, idempotency_key
        )
    except VideoAnalysisConflict as exc:
        raise HTTPException(status_code=409, detail="Idempotency key conflict") from exc
    except VideoAnalysisCapacityExceeded as exc:
        raise HTTPException(
            status_code=429,
            detail="Video analysis capacity is temporarily full",
        ) from exc
    except PayloadEnvelopeError as exc:
        raise HTTPException(
            status_code=503, detail="Video analysis encryption is not configured"
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if not created:
        response.status_code = status.HTTP_200_OK
    public_result = {
        key: value for key, value in accepted.items() if key != "task_id"
    }
    return {**public_result, "created": created}


@router.delete("/analyses/{analysis_id}")
def cancel_video_analysis(
    analysis_id: UUID,
    user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> dict[str, object]:
    """Cancel queued analysis or request cooperative cancellation of running work."""
    try:
        result = _analysis_jobs().cancel(user.user_id, analysis_id)
    except VideoAnalysisConflict as exc:
        raise HTTPException(
            status_code=409,
            detail="Video analysis cannot be cancelled in its current state",
        ) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Video analysis not found")
    return result


@router.get("/analyses/{analysis_id}")
def get_video_analysis(
    analysis_id: UUID,
    user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> dict[str, object]:
    """Read analysis status and result only for the authenticated owner."""
    analysis = _analysis_jobs().get(user.user_id, analysis_id)
    if analysis is None:
        raise HTTPException(status_code=404, detail="Video analysis not found")
    return analysis



@router.post("/analyses/{analysis_id}/prompts/compose")
def compose_prompt_from_analysis(
    analysis_id: UUID,
    payload: AnalysisPromptOptions,
    user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> dict[str, object]:
    """Compose original generation prompts from an owned completed analysis; never execute them."""
    analysis = _analysis_jobs().get(user.user_id, analysis_id)
    if analysis is None:
        raise HTTPException(status_code=404, detail="Video analysis not found")
    if analysis["status"] != "completed":
        raise HTTPException(
            status_code=409,
            detail={
                "code": "analysis_not_completed",
                "message": "Video analysis must complete before prompt composition",
            },
        )
    result = analysis.get("result")
    if not isinstance(result, dict):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "analysis_result_unavailable",
                "message": "Video analysis result is unavailable",
            },
        )
    try:
        prompts = compose_prompts_from_analysis(result, payload)
    except PromptCompositionUnavailable as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
    return {
        "analysis_id": str(analysis_id),
        "status": "composed",
        "execution": "not_started",
        "mode": result.get("mode"),
        "prompts": prompts,
        "count": len(prompts),
    }


class TimelineDraftCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    analysis_id: UUID
    asset_id: UUID
    duration_seconds: int = Field(ge=3, le=60)
    aspect_ratio: Literal["9:16", "16:9", "1:1", "4:5"]
    beats: list[TimelineBeat] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def validate_beats(self) -> "TimelineDraftCreateRequest":
        previous_end = 0.0
        for beat in self.beats:
            if beat.end_seconds > self.duration_seconds:
                raise ValueError("Timeline beat exceeds draft duration")
            if beat.start_seconds < previous_end:
                raise ValueError("Timeline beats must be ordered and cannot overlap")
            previous_end = beat.end_seconds
        return self


@router.post("/timeline-drafts", status_code=status.HTTP_201_CREATED)
def create_timeline_draft(
    payload: TimelineDraftCreateRequest,
    user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> dict[str, object]:
    """Create an editable timeline only for an asset in the owner's completed analysis."""
    analysis = _analysis_jobs().get(user.user_id, payload.analysis_id)
    if analysis is None:
        raise HTTPException(status_code=404, detail="Video analysis not found")
    if analysis["status"] != "completed" or not isinstance(analysis.get("result"), dict):
        raise HTTPException(status_code=409, detail="Video analysis is not completed")
    assets = analysis["result"].get("assets")
    if not isinstance(assets, list) or not any(
        isinstance(item, dict) and item.get("asset_id") == str(payload.asset_id)
        for item in assets
    ):
        raise HTTPException(status_code=404, detail="Asset is not part of this analysis")
    try:
        return _timeline_drafts().create(
            user.user_id,
            payload.analysis_id,
            payload.asset_id,
            payload.duration_seconds,
            payload.aspect_ratio,
            [beat.model_dump(mode="json") for beat in payload.beats],
        )
    except TimelineConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/timeline-drafts/{draft_id}")
def get_timeline_draft(
    draft_id: UUID,
    user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> dict[str, object]:
    draft = _timeline_drafts().get(user.user_id, draft_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="Timeline draft not found")
    return draft


@router.put("/timeline-drafts/{draft_id}")
def update_timeline_draft(
    draft_id: UUID,
    payload: TimelineDraftUpdate,
    user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> dict[str, object]:
    try:
        draft = _timeline_drafts().update(user.user_id, draft_id, payload)
    except TimelineConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if draft is None:
        raise HTTPException(status_code=404, detail="Timeline draft not found")
    return draft
