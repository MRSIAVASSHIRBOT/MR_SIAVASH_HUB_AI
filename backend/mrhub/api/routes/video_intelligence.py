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
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from mrhub.api.dependencies import require_user
from mrhub.config import get_settings
from mrhub.jobs.payload_envelope import PayloadEnvelopeError
from mrhub.media.repository import MediaAssetRepository
from mrhub.security.auth import AuthenticatedUser
from mrhub.video_intelligence.generation import VideoGenerationRequest
from mrhub.video_intelligence.generation_jobs import (
    VideoGenerationConflict,
    VideoGenerationJobRepository,
)
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
from mrhub.video_intelligence.render_jobs import (
    VideoRenderConflict,
    VideoRenderJobRepository,
)
from mrhub.video_intelligence.repository import VideoBrandRepository
from mrhub.video_intelligence.schemas import (
    BeatInstruction,
    BrandIdentity,
    VideoAnalysisRequest,
    VideoTechnicalMetadata,
)
from mrhub.video_intelligence.service import build_generation_prompt, probe_video
from mrhub.video_intelligence.timeline_drafts import (
    TimelineBeat,
    TimelineConflict,
    TimelineDraftUpdate,
    VideoTimelineDraftRepository,
)

router = APIRouter(
    prefix="/video-intelligence",
    tags=["video-intelligence"],
    dependencies=[Depends(require_user)],
)


class GenerationSubmissionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str = Field(min_length=1, max_length=80)
    model: str = Field(min_length=1, max_length=120)
    prompt: str = Field(min_length=1, max_length=20_000)
    aspect_ratio: str = Field(pattern=r"^(9:16|16:9|1:1|4:5)$")
    duration_seconds: int = Field(ge=3, le=60)
    resolution: str = Field(default="720p", pattern=r"^(720p|1080p)$")


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
    timeline_draft_id: UUID | None = None
    timeline_draft_version: int | None = Field(default=None, ge=1, strict=True)

    @model_validator(mode="after")
    def validate_timeline(self) -> PromptCompositionRequest:
        if any(beat.end_seconds > self.duration_seconds for beat in self.beats):
            raise ValueError("Beat timeline cannot exceed the requested duration")
        if (self.timeline_draft_id is None) != (self.timeline_draft_version is None):
            raise ValueError("Timeline draft ID and version must be supplied together")
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




@router.post("/analyses/{analysis_id}/generations", status_code=status.HTTP_202_ACCEPTED)
def submit_video_generation(
    analysis_id: UUID,
    payload: GenerationSubmissionRequest,
    response: Response,
    user: Annotated[AuthenticatedUser, Depends(require_user)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> dict[str, object]:
    """Create an owner-scoped generation task that cannot run before explicit approval."""
    from mrhub.domain.tasks import TaskStatus
    from mrhub.video_intelligence.generation_registry import video_generation_registry

    try:
        provider = video_generation_registry.get(payload.provider, payload.model)
    except LookupError as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": "provider_unavailable", "execution": "not_started"},
        ) from exc
    capability = provider.capability
    if (
        payload.duration_seconds > capability.max_duration_seconds
        or payload.aspect_ratio not in capability.supported_aspect_ratios
        or (payload.resolution == "1080p" and capability.max_resolution != "1080p")
    ):
        raise HTTPException(
            status_code=422,
            detail={"code": "provider_capability_mismatch"},
        )

    request = VideoGenerationRequest(
        prompt=payload.prompt,
        aspect_ratio=payload.aspect_ratio,
        duration_seconds=payload.duration_seconds,
        resolution=payload.resolution,
        idempotency_key=idempotency_key,
    )
    jobs = VideoGenerationJobRepository(get_settings().database_path)
    try:
        accepted, created = jobs.submit(
            user.user_id, analysis_id, payload.provider, payload.model, request
        )
        generation_id = UUID(str(accepted["generation_id"]))
        linked = jobs.enqueue(user.user_id, generation_id)
        if linked is None:
            raise ValueError("Generation job disappeared before task handoff")
        task_id = UUID(str(linked["task_id"]))
        task = jobs.tasks.get(task_id)
        if task is None:
            raise ValueError("Generation task could not be read back")
        generation = jobs.get(user.user_id, generation_id)
        if generation is None:
            raise ValueError("Generation job could not be read back")
    except VideoGenerationConflict as exc:
        raise HTTPException(status_code=409, detail="Idempotency key conflict") from exc
    except PayloadEnvelopeError as exc:
        raise HTTPException(
            status_code=503, detail="Video generation encryption is not configured"
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if not created:
        response.status_code = status.HTTP_200_OK
    awaiting_approval = task.status is TaskStatus.WAITING_APPROVAL
    return {
        "generation_id": str(generation_id),
        "task_id": str(task_id),
        "status": task.status.value,
        "generation_status": generation["status"],
        "provider": payload.provider,
        "model": payload.model,
        "created": created,
        "approval_required": awaiting_approval,
        "approval_endpoint": f"/tasks/{task_id}/approval",
        "execution": "awaiting_approval" if awaiting_approval else "queued_or_terminal",
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
    draft: dict[str, object] | None = None
    if payload.timeline_draft_id is not None:
        draft = _timeline_drafts().get(user.user_id, payload.timeline_draft_id)
        if draft is None:
            raise HTTPException(status_code=404, detail="Timeline draft not found")
        if draft.get("analysis_id") != str(analysis_id):
            raise HTTPException(
                status_code=409,
                detail={"code": "timeline_draft_analysis_mismatch"},
            )
        if draft.get("version") != payload.timeline_draft_version:
            raise HTTPException(
                status_code=409,
                detail={"code": "timeline_draft_version_conflict"},
            )
        try:
            validated_draft = TimelineDraftUpdate(
                expected_version=payload.timeline_draft_version,
                duration_seconds=draft.get("duration_seconds"),
                aspect_ratio=draft.get("aspect_ratio"),
                beats=draft.get("beats"),
            )
        except ValidationError:
            raise HTTPException(
                status_code=409,
                detail={"code": "timeline_draft_invalid"},
            ) from None
        draft = {
            **draft,
            "beats": [beat.model_dump(mode="json") for beat in validated_draft.beats],
        }

    try:
        prompts = compose_prompts_from_analysis(
            result,
            payload,
            timeline_draft=draft,
            expected_analysis_id=str(analysis_id),
        )
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
        "timeline_draft": (
            {
                "draft_id": draft["draft_id"],
                "asset_id": draft["asset_id"],
                "version": draft["version"],
            }
            if draft is not None
            else None
        ),
    }


class TimelineDraftCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    analysis_id: UUID
    asset_id: UUID
    duration_seconds: int = Field(ge=3, le=60)
    aspect_ratio: Literal["9:16", "16:9", "1:1", "4:5"]
    beats: list[TimelineBeat] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def validate_beats(self) -> TimelineDraftCreateRequest:
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


def _render_jobs() -> VideoRenderJobRepository:
    return VideoRenderJobRepository(get_settings().database_path)


@router.post("/analyses/{analysis_id}/renders", status_code=status.HTTP_202_ACCEPTED)
def submit_video_render(
    analysis_id: UUID,
    response: Response,
    user: Annotated[AuthenticatedUser, Depends(require_user)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> dict[str, object]:
    """Queue a silent cut-only MP4 render from a completed owned analysis."""
    try:
        accepted, created = _render_jobs().submit(
            user.user_id, analysis_id, idempotency_key
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="Video analysis not found") from exc
    except VideoRenderConflict as exc:
        raise HTTPException(status_code=409, detail="Idempotency key conflict") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not created:
        response.status_code = status.HTTP_200_OK
    return {
        key: value for key, value in accepted.items() if key != "task_id"
    } | {"created": created}


@router.get("/renders/{render_id}")
def get_video_render(
    render_id: UUID,
    user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> dict[str, object]:
    """Read render status only for the authenticated owner."""
    render = _render_jobs().get(user.user_id, render_id)
    if render is None:
        raise HTTPException(status_code=404, detail="Video render not found")
    return render


@router.delete("/renders/{render_id}")
def cancel_video_render(
    render_id: UUID,
    user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> dict[str, object]:
    """Cancel queued rendering or request cooperative cancellation of running work."""
    result = _render_jobs().cancel(user.user_id, render_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Video render not found")
    return result
