"""Validated contracts for video style analysis and prompt generation."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class AnalysisMode(StrEnum):
    FAITHFUL = "faithful_style_reconstruction"
    FUSION = "creative_style_fusion"


class BrandIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    brand_name: str = Field(min_length=1, max_length=80)
    handle: str | None = Field(default=None, max_length=80)
    logo_asset_id: str | None = Field(default=None, max_length=64)
    colors: list[str] = Field(default_factory=list, max_length=8)
    font_preferences: list[str] = Field(default_factory=list, max_length=8)
    tone: str | None = Field(default=None, max_length=240)


class VideoAnalysisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: AnalysisMode
    source_asset_ids: list[str] = Field(min_length=1, max_length=5)
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
