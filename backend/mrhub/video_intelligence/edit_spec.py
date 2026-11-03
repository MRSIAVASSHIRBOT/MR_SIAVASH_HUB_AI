"""Deterministic, validated edit specifications derived from bounded analysis."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from mrhub.video_intelligence.schemas import AnalysisMode, BrandIdentity, VideoAnalysisRequest

DirectiveKey = Annotated[str, Field(min_length=1, max_length=64)]
DirectiveValue = Annotated[str, Field(max_length=500)]


class EditSourceReference(BaseModel):
    """Evidence and scene map for one owner-authorized source asset."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    asset_id: str = Field(min_length=1, max_length=64)
    source_duration_seconds: float = Field(gt=0, le=60)
    scene_start_timestamps: list[float] = Field(min_length=1, max_length=25)
    scene_boundaries_truncated: bool = False
    visual_style_summary: str | None = Field(default=None, max_length=1000)


class BrandGuidance(BaseModel):
    """Brand constraints prepared for a later renderer; not applied to pixels."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["not_provided", "guidance_prepared"] = "not_provided"
    brand_name: str | None = Field(default=None, max_length=80)
    handle: str | None = Field(default=None, max_length=80)
    logo_asset_id: str | None = Field(default=None, max_length=64)
    colors: list[str] = Field(default_factory=list, max_length=8)
    font_preferences: list[str] = Field(default_factory=list, max_length=8)
    tone: str | None = Field(default=None, max_length=240)


class CustomEditGuidance(BaseModel):
    """Bounded user requirements, retained as data rather than executable prompts."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["none", "guidance_prepared"] = "none"
    directives: dict[DirectiveKey, DirectiveValue] = Field(default_factory=dict, max_length=12)


class EditSpecification(BaseModel):
    """Renderer-facing contract; its status explicitly prevents false render claims."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    schema_version: Literal["1.0"] = "1.0"
    mode: AnalysisMode
    style_strategy: Literal["preserve_reference", "reference_plus_user_direction"]
    output_aspect_ratio: Literal["9:16", "16:9", "1:1", "4:5"]
    requested_output_duration_seconds: int = Field(ge=3, le=60)
    sources: list[EditSourceReference] = Field(min_length=1, max_length=5)
    brand_guidance: BrandGuidance
    custom_edit_guidance: CustomEditGuidance
    audio_plan_status: Literal["not_requested", "requested_not_implemented"]
    timeline_status: Literal["scene_map_prepared_timeline_not_built"] = (
        "scene_map_prepared_timeline_not_built"
    )
    render_status: Literal["not_implemented"] = "not_implemented"


def build_edit_specification(
    request: VideoAnalysisRequest,
    asset_results: list[dict[str, object]],
) -> EditSpecification:
    """Build a deterministic edit contract without claiming rendering or application."""
    sources: list[EditSourceReference] = []
    for item in asset_results:
        metadata = item.get("technical_metadata")
        if not isinstance(metadata, dict):
            raise ValueError("Technical metadata is required for edit specification")
        duration = item.get("analysis_window_seconds")
        scene_starts = item.get("scene_start_timestamps")
        semantic = item.get("semantic_visual_analysis")
        if not isinstance(duration, (int, float)) or isinstance(duration, bool):
            raise ValueError("Source duration is invalid")
        if not isinstance(scene_starts, list):
            raise ValueError("Scene map is invalid")
        summary: str | None = None
        if isinstance(semantic, dict) and semantic.get("status") == "completed":
            candidate = semantic.get("style_summary")
            if isinstance(candidate, str):
                summary = candidate
        sources.append(
            EditSourceReference(
                asset_id=str(item["asset_id"]),
                source_duration_seconds=float(duration),
                scene_start_timestamps=scene_starts,
                scene_boundaries_truncated=bool(item.get("scene_boundaries_truncated", False)),
                visual_style_summary=summary,
            )
        )

    brand = request.brand
    brand_guidance = (
        BrandGuidance(
            status="guidance_prepared",
            brand_name=brand.brand_name,
            handle=brand.handle,
            logo_asset_id=brand.logo_asset_id,
            colors=brand.colors,
            font_preferences=brand.font_preferences,
            tone=brand.tone,
        )
        if brand is not None
        else BrandGuidance()
    )
    custom_guidance = (
        CustomEditGuidance(status="guidance_prepared", directives=request.custom_changes)
        if request.custom_changes
        else CustomEditGuidance()
    )
    return EditSpecification(
        mode=request.mode,
        style_strategy=(
            "preserve_reference"
            if request.mode is AnalysisMode.FAITHFUL
            else "reference_plus_user_direction"
        ),
        output_aspect_ratio=request.output_aspect_ratio,
        requested_output_duration_seconds=request.duration_seconds,
        sources=sources,
        brand_guidance=brand_guidance,
        custom_edit_guidance=custom_guidance,
        audio_plan_status=(
            "requested_not_implemented" if request.include_audio_analysis else "not_requested"
        ),
    )
