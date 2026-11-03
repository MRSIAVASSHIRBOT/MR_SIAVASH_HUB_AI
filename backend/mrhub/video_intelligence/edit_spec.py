"""Deterministic, validated edit specifications derived from bounded analysis."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from mrhub.video_intelligence.schemas import AnalysisMode, VideoAnalysisRequest

DirectiveKey = Annotated[str, Field(min_length=1, max_length=64)]
DirectiveValue = Annotated[str, Field(max_length=500)]


class EditSourceReference(BaseModel):
    """Evidence and scene map for one owner-authorized source asset."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    asset_id: str = Field(min_length=1, max_length=64)
    source_duration_seconds: float = Field(gt=0, le=60)
    width: int | None = Field(default=None, ge=1, le=16384)
    height: int | None = Field(default=None, ge=1, le=16384)
    frame_rate: float | None = Field(default=None, ge=0, le=240)
    codec: str | None = Field(default=None, max_length=40)
    has_audio: bool | None = None
    scene_start_timestamps: list[float] = Field(min_length=1, max_length=25)
    scene_boundaries_truncated: bool = False
    visual_style_summary: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def validate_scene_map(self) -> EditSourceReference:
        starts = self.scene_start_timestamps
        if starts[0] != 0.0 or starts != sorted(set(starts)):
            raise ValueError("Scene map must start at zero and be strictly increasing")
        if any(value < 0 or value >= self.source_duration_seconds for value in starts):
            raise ValueError("Scene boundary is outside the analyzed source duration")
        return self


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
            raise TypeError("Technical metadata is required for edit specification")
        duration = item.get("analysis_window_seconds")
        scene_starts = item.get("scene_start_timestamps")
        semantic = item.get("semantic_visual_analysis")
        if not isinstance(duration, (int, float)) or isinstance(duration, bool):
            raise TypeError("Source duration is invalid")
        if not isinstance(scene_starts, list):
            raise TypeError("Scene map is invalid")
        summary: str | None = None
        if isinstance(semantic, dict) and semantic.get("status") == "completed":
            candidate = semantic.get("style_summary")
            if isinstance(candidate, str):
                summary = candidate
        sources.append(
            EditSourceReference(
                asset_id=str(item["asset_id"]),
                source_duration_seconds=float(duration),
                width=metadata.get("width"),
                height=metadata.get("height"),
                frame_rate=metadata.get("frame_rate"),
                codec=metadata.get("codec"),
                has_audio=metadata.get("has_audio"),
                # FFmpeg's parser allows a small timestamp tolerance around EOF.
                # A cut at/after the analyzed duration cannot start an output segment.
                scene_start_timestamps=[
                    value for value in scene_starts
                    if isinstance(value, (int, float))
                    and not isinstance(value, bool)
                    and value < float(duration)
                ],
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
