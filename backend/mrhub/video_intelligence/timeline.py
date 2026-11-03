"""Validated, deterministic cut-only timelines derived from edit specifications."""

from __future__ import annotations

import math
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from mrhub.video_intelligence.edit_spec import EditSpecification


class TimelineClip(BaseModel):
    """One source interval placed contiguously on the primary video track."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    clip_id: str = Field(min_length=1, max_length=32)
    source_asset_id: str = Field(min_length=1, max_length=64)
    source_scene_index: int = Field(ge=0, le=24)
    source_start_seconds: float = Field(ge=0, le=60)
    source_end_seconds: float = Field(gt=0, le=60)
    timeline_start_seconds: float = Field(ge=0, le=60)
    timeline_end_seconds: float = Field(gt=0, le=60)
    transition_in: Literal["none", "cut"] = "cut"

    @model_validator(mode="after")
    def validate_intervals(self) -> TimelineClip:
        source_duration = self.source_end_seconds - self.source_start_seconds
        timeline_duration = self.timeline_end_seconds - self.timeline_start_seconds
        if source_duration <= 0 or timeline_duration <= 0:
            raise ValueError("Timeline clip intervals must have positive duration")
        if not math.isclose(source_duration, timeline_duration, abs_tol=0.001):
            raise ValueError("Source and timeline clip durations must match")
        return self


class VideoTimeline(BaseModel):
    """Renderer-neutral timeline; no command strings or executable filters."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    schema_version: Literal["1.0"] = "1.0"
    output_aspect_ratio: Literal["9:16", "16:9", "1:1", "4:5"]
    requested_duration_seconds: int = Field(ge=3, le=60)
    actual_duration_seconds: float = Field(gt=0, le=60)
    duration_shortfall_seconds: float = Field(ge=0, le=60)
    video_track: list[TimelineClip] = Field(min_length=1, max_length=125)
    audio_track_status: Literal["not_requested", "requested_not_implemented"]
    timeline_status: Literal["validated_cut_only"]
    render_status: Literal["not_implemented"]

    @model_validator(mode="after")
    def validate_track(self) -> VideoTimeline:
        clips = self.video_track
        if clips[0].timeline_start_seconds != 0:
            raise ValueError("Timeline must begin at zero")
        for previous, current in zip(clips, clips[1:]):
            if not math.isclose(
                previous.timeline_end_seconds,
                current.timeline_start_seconds,
                abs_tol=0.001,
            ):
                raise ValueError("Video track must be contiguous without overlaps or gaps")
        if not math.isclose(
            clips[-1].timeline_end_seconds,
            self.actual_duration_seconds,
            abs_tol=0.001,
        ):
            raise ValueError("Actual duration must match the final clip boundary")
        if not math.isclose(
            self.requested_duration_seconds - self.actual_duration_seconds,
            self.duration_shortfall_seconds,
            abs_tol=0.001,
        ):
            raise ValueError("Duration shortfall does not match requested and actual durations")
        if self.actual_duration_seconds > self.requested_duration_seconds:
            raise ValueError("Timeline cannot exceed requested output duration")
        return self


def build_video_timeline(specification: EditSpecification) -> VideoTimeline:
    """Allocate output time evenly across available sources, then cut at scene boundaries.

    Each source receives an equal share of the remaining output budget. If a source
    is shorter than its share, the unused time is redistributed across later sources.
    Scene cuts are retained where possible; the final scene in each allocation may
    be trimmed. The result contains only numeric edit decisions, never shell/FFmpeg
    command fragments.
    """
    clips: list[TimelineClip] = []
    timeline_cursor = 0.0
    remaining_budget = float(specification.requested_output_duration_seconds)
    remaining_sources = len(specification.sources)

    for source in specification.sources:
        if remaining_sources <= 0 or remaining_budget <= 0:
            break
        allocation = min(
            source.source_duration_seconds,
            remaining_budget / remaining_sources,
        )
        remaining_sources -= 1
        remaining_budget = max(0.0, remaining_budget - allocation)
        if allocation <= 0:
            continue

        scene_starts = source.scene_start_timestamps
        for scene_index, scene_start in enumerate(scene_starts):
            if scene_start >= allocation:
                break
            next_scene_start = (
                scene_starts[scene_index + 1]
                if scene_index + 1 < len(scene_starts)
                else source.source_duration_seconds
            )
            source_end = min(next_scene_start, allocation)
            if source_end <= scene_start:
                continue
            clip_duration = source_end - scene_start
            timeline_end = timeline_cursor + clip_duration
            clips.append(
                TimelineClip(
                    clip_id=f"clip-{len(clips) + 1:03d}",
                    source_asset_id=source.asset_id,
                    source_scene_index=scene_index,
                    source_start_seconds=round(scene_start, 3),
                    source_end_seconds=round(source_end, 3),
                    timeline_start_seconds=round(timeline_cursor, 3),
                    timeline_end_seconds=round(timeline_end, 3),
                    transition_in="none" if not clips else "cut",
                )
            )
            timeline_cursor = timeline_end
            if timeline_cursor >= specification.requested_output_duration_seconds:
                break
        if timeline_cursor >= specification.requested_output_duration_seconds:
            break

    actual_duration = round(timeline_cursor, 3)
    if not clips or actual_duration <= 0:
        raise ValueError("No usable source intervals are available for the timeline")

    return VideoTimeline(
        output_aspect_ratio=specification.output_aspect_ratio,
        requested_duration_seconds=specification.requested_output_duration_seconds,
        actual_duration_seconds=actual_duration,
        duration_shortfall_seconds=round(
            specification.requested_output_duration_seconds - actual_duration, 3
        ),
        video_track=clips,
        audio_track_status=specification.audio_plan_status,
        timeline_status="validated_cut_only",
        render_status="not_implemented",
    )
