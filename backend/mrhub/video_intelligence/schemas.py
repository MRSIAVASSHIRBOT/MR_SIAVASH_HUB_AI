"""Validated contracts for video style analysis and prompt generation."""

# ruff: noqa: I001 -- retain standard-library-first grouping for typing and Pydantic.

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


ShortText = Annotated[str, Field(max_length=40)]


class AnalysisMode(StrEnum):
    FAITHFUL = "faithful_style_reconstruction"
    FUSION = "creative_style_fusion"


class BeatInstruction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start_seconds: float = Field(ge=0, le=60)
    end_seconds: float = Field(gt=0, le=60)
    generation_instruction: str = Field(min_length=1, max_length=1200)
    transition_to_next: str = Field(default="clean cinematic cut", max_length=240)

    @model_validator(mode="after")
    def validate_interval(self) -> BeatInstruction:
        if self.end_seconds <= self.start_seconds:
            raise ValueError("Beat end must be after its start")
        return self


class BrandIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    brand_name: str = Field(min_length=1, max_length=80)
    handle: str | None = Field(default=None, max_length=80)
    logo_asset_id: str | None = Field(default=None, max_length=64)
    colors: list[ShortText] = Field(default_factory=list, max_length=8)
    font_preferences: list[ShortText] = Field(default_factory=list, max_length=8)
    tone: str | None = Field(default=None, max_length=240)


class VideoAnalysisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: AnalysisMode
    source_asset_ids: list[Annotated[str, Field(min_length=1, max_length=64)]] = Field(min_length=1, max_length=5)
    brand: BrandIdentity | None = None
    duration_seconds: int = Field(default=10, ge=3, le=60)
    output_aspect_ratio: Literal["9:16", "16:9", "1:1", "4:5"] = "9:16"
    include_audio_analysis: bool = True
    custom_changes: dict[str, str] = Field(default_factory=dict, max_length=12)


class VideoTechnicalMetadata(BaseModel):
    duration_seconds: float | None = None
    width: int | None = None
    height: int | None = None
    frame_rate: float | None = None
    codec: str | None = None
    has_audio: bool | None = None
    metadata_status: Literal["available", "ffprobe_unavailable", "probe_failed"]


class VideoAnalysisAccepted(BaseModel):
    analysis_id: str
    status: Literal["accepted"] = "accepted"
    mode: AnalysisMode
    message: str
