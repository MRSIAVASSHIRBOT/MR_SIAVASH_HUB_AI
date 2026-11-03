"""Strict, evidence-linked schema for local semantic frame observations."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

ColorNote = Annotated[str, Field(min_length=1, max_length=40)]


class VisualFrameObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    timestamp_seconds: float = Field(ge=0, le=60)
    description: str = Field(min_length=1, max_length=600)
    shot_scale: Literal[
        "extreme_wide", "wide", "medium", "close_up", "extreme_close_up", "unclear"
    ] = "unclear"
    camera_movement: Literal[
        "static", "pan", "tilt", "tracking", "zoom", "handheld", "unclear"
    ] = "unclear"
    composition: str = Field(default="", max_length=240)
    lighting: str = Field(default="", max_length=180)
    color_notes: list[ColorNote] = Field(default_factory=list, max_length=6)
    confidence: float = Field(ge=0, le=1)


class VisualAnalysisResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    style_summary: str = Field(min_length=1, max_length=1000)
    observations: list[VisualFrameObservation] = Field(min_length=1, max_length=12)

    @model_validator(mode="after")
    def validate_unique_timestamps(self) -> VisualAnalysisResult:
        timestamps = [item.timestamp_seconds for item in self.observations]
        if len(timestamps) != len(set(timestamps)):
            raise ValueError("Visual observations must have unique timestamps")
        return self
