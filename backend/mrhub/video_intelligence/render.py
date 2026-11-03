"""Bounded FFmpeg renderer for validated cut-only video timelines.

This module accepts only validated numeric timeline data and trusted local paths.
It deliberately renders a silent video track; audio, text, graphics, and transitions
other than hard cuts remain outside this renderer's contract.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError

from mrhub.media.repository import MAX_OUTPUT_BYTES
from mrhub.video_intelligence.timeline import VideoTimeline

MAX_RENDER_CLIPS = 125
MAX_RENDER_DURATION_SECONDS = 60
MAX_RENDER_DIMENSION = 1920
MAX_RENDER_TIMEOUT_SECONDS = 180
MAX_PROBE_OUTPUT_BYTES = 16_384
OUTPUT_DIMENSIONS = {
    "9:16": (1080, 1920),
    "16:9": (1920, 1080),
    "1:1": (1080, 1080),
    "4:5": (1080, 1350),
}


class VideoRenderError(RuntimeError):
    """A safe, stable failure code for bounded video rendering."""

    def __init__(self, reason_code: str) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code


@dataclass(frozen=True)
class VideoRenderResult:
    """Verified metadata for one atomically published MP4 output."""

    output_path: Path
    duration_seconds: float
    width: int
    height: int
    file_size: int


def _seconds(value: float) -> str:
    # Timeline models reject NaN/Infinity; fixed precision keeps generated
    # filter expressions numeric and prevents user-controlled filter syntax.
    return f"{value:.3f}"


def build_ffmpeg_command(
    *,
    ffmpeg_binary: str,
    timeline: VideoTimeline,
    source_paths: dict[str, Path],
    temporary_output: Path,
) -> list[str]:
    """Build a deterministic FFmpeg argv from a validated cut-only timeline."""
    if len(timeline.video_track) > MAX_RENDER_CLIPS:
        raise VideoRenderError("render_clip_limit_exceeded")
    if not 0 < timeline.actual_duration_seconds <= MAX_RENDER_DURATION_SECONDS:
        raise VideoRenderError("render_duration_out_of_range")
    dimensions = OUTPUT_DIMENSIONS.get(timeline.output_aspect_ratio)
    if dimensions is None:
        raise VideoRenderError("render_aspect_ratio_unsupported")
    width, height = dimensions
    if max(width, height) > MAX_RENDER_DIMENSION:
        raise VideoRenderError("render_dimensions_out_of_range")

    command = [
        ffmpeg_binary,
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "error",
        "-max_pixels",
        "33554432",
        "-threads",
        "2",
        "-filter_threads",
        "1",
        "-filter_complex_threads",
        "1",
        "-y",
    ]
    filter_parts: list[str] = []
    labels: list[str] = []
    for index, clip in enumerate(timeline.video_track):
        source = source_paths.get(clip.source_asset_id)
        if source is None:
            raise VideoRenderError("render_source_missing")
        if not source.is_file():
            raise VideoRenderError("render_source_file_missing")
        command.extend(["-protocol_whitelist", "file,pipe", "-i", str(source)])
        label = f"v{index}"
        labels.append(f"[{label}]")
        filter_parts.append(
            f"[{index}:v:0]"
            f"trim=start={_seconds(clip.source_start_seconds)}:"
            f"end={_seconds(clip.source_end_seconds)},"
            "setpts=PTS-STARTPTS,"
            f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,"
            "setsar=1,fps=30,format=yuv420p"
            f"[{label}]"
        )

    concat_inputs = "".join(labels)
    filter_parts.append(
        f"{concat_inputs}concat=n={len(labels)}:v=1:a=0[outv]"
    )
    command.extend(
        [
            "-filter_complex",
            ";".join(filter_parts),
            "-map",
            "[outv]",
            "-an",
            "-t",
            _seconds(timeline.actual_duration_seconds),
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "23",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            "-threads",
            "2",
            "-fs",
            str(MAX_OUTPUT_BYTES),
            "-f",
            "mp4",
            str(temporary_output),
        ]
    )
    return command


def render_video_timeline(
    *,
    timeline: VideoTimeline | dict[str, object],
    source_paths: dict[str, Path],
    output_path: Path,
    ffmpeg_binary: str | None = None,
    ffprobe_binary: str | None = None,
    timeout_seconds: int = MAX_RENDER_TIMEOUT_SECONDS,
) -> VideoRenderResult:
    """Render and verify a silent MP4, publishing it only after successful probing.

    The caller must resolve every source asset through the authenticated owner's
    media repository immediately before calling this function. This function
    independently validates the timeline, local file existence, output location,
    process bounds, and generated MP4 metadata.
    """
    try:
        validated = (
            timeline
            if isinstance(timeline, VideoTimeline)
            else VideoTimeline.model_validate(timeline)
        )
    except (ValidationError, TypeError, ValueError) as exc:
        raise VideoRenderError("render_timeline_invalid") from exc

    ffmpeg = ffmpeg_binary or shutil.which("ffmpeg")
    ffprobe = ffprobe_binary or shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        raise VideoRenderError("ffmpeg_unavailable")
    if not 1 <= timeout_seconds <= MAX_RENDER_TIMEOUT_SECONDS:
        raise VideoRenderError("render_timeout_out_of_range")
    if output_path.suffix.lower() != ".mp4" or not output_path.parent.is_dir():
        raise VideoRenderError("render_output_target_invalid")
    if output_path.exists():
        raise VideoRenderError("render_output_target_exists")

    # Resolve and validate every referenced source before starting a process.
    referenced = {clip.source_asset_id for clip in validated.video_track}
    resolved_sources: dict[str, Path] = {}
    for asset_id in referenced:
        candidate = source_paths.get(asset_id)
        if candidate is None:
            raise VideoRenderError("render_source_missing")
        try:
            resolved = candidate.resolve(strict=True)
        except OSError as exc:
            raise VideoRenderError("render_source_file_missing") from exc
        if not resolved.is_file():
            raise VideoRenderError("render_source_file_missing")
        resolved_sources[asset_id] = resolved

    temporary_output = output_path.with_name(
        f".{output_path.stem}.{uuid4().hex}.partial.mp4"
    )
    command = build_ffmpeg_command(
        ffmpeg_binary=ffmpeg,
        timeline=validated,
        source_paths=resolved_sources,
        temporary_output=temporary_output,
    )
    environment = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": str(output_path.parent.resolve()),
        "TMPDIR": str(output_path.parent.resolve()),
        "LANG": "C",
        "LC_ALL": "C",
    }
    try:
        try:
            completed = subprocess.run(
                command,
                shell=False,
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=timeout_seconds,
                env=environment,
            )
        except subprocess.TimeoutExpired as exc:
            raise VideoRenderError("render_timeout") from exc
        except OSError as exc:
            raise VideoRenderError("ffmpeg_unavailable") from exc
        if completed.returncode != 0:
            raise VideoRenderError("ffmpeg_failed")
        if not temporary_output.is_file():
            raise VideoRenderError("render_output_missing")
        size = temporary_output.stat().st_size
        if size <= 0 or size > MAX_OUTPUT_BYTES:
            raise VideoRenderError("render_output_size_invalid")

        try:
            probe = subprocess.run(
                [
                    ffprobe,
                    "-v",
                    "error",
                    "-protocol_whitelist",
                    "file,pipe",
                    "-max_streams",
                    "8",
                    "-max_alloc",
                    "33554432",
                    "-show_entries",
                    "format=format_name,duration:stream=codec_type,width,height",
                    "-of",
                    "json",
                    str(temporary_output),
                ],
                shell=False,
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                timeout=10,
                env=environment,
            )
        except (subprocess.TimeoutExpired, OSError) as exc:
            raise VideoRenderError("render_output_probe_failed") from exc
        if probe.returncode != 0 or len(probe.stdout) > MAX_PROBE_OUTPUT_BYTES:
            raise VideoRenderError("render_output_probe_failed")
        try:
            metadata = json.loads(probe.stdout)
            format_info = metadata["format"]
            streams = metadata["streams"]
            duration = float(format_info["duration"])
            video_streams = [
                stream for stream in streams if stream.get("codec_type") == "video"
            ]
            width, height = OUTPUT_DIMENSIONS[validated.output_aspect_ratio]
            if (
                "mp4" not in str(format_info["format_name"]).split(",")
                or len(video_streams) != 1
                or int(video_streams[0]["width"]) != width
                or int(video_streams[0]["height"]) != height
                or not 0 < duration <= validated.actual_duration_seconds + 0.5
                or duration < validated.actual_duration_seconds - 0.5
            ):
                raise VideoRenderError("render_output_verification_failed")
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise VideoRenderError("render_output_verification_failed") from exc

        os.replace(temporary_output, output_path)
        return VideoRenderResult(
            output_path=output_path,
            duration_seconds=duration,
            width=width,
            height=height,
            file_size=size,
        )
    finally:
        temporary_output.unlink(missing_ok=True)