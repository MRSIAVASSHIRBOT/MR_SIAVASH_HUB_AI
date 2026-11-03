"""Safe, dependency-light primitives for video intelligence workflows.

This first slice deliberately does not download URLs or execute media tools.
It probes only server-owned asset paths supplied by the authenticated media
repository in a later integration layer.
"""

import json
import math
import pathlib
import shutil
import subprocess
from typing import Any

from mrhub.video_intelligence.schemas import VideoTechnicalMetadata

_PROBE_TIMEOUT_SECONDS = 12
_MAX_PROBE_OUTPUT_BYTES = 256 * 1024
_MAX_PROBE_STREAMS = 64


def probe_video(path: pathlib.Path) -> VideoTechnicalMetadata:
    """Return measurable technical metadata using ffprobe when installed."""
    binary = shutil.which("ffprobe")
    if binary is None:
        return VideoTechnicalMetadata(metadata_status="ffprobe_unavailable")
    if not path.is_file():
        return VideoTechnicalMetadata(metadata_status="probe_failed")

    command = [
        binary,
        "-v", "error",
        "-max_streams", str(_MAX_PROBE_STREAMS),
        "-show_entries", "format=duration:stream=codec_type,codec_name,width,height,avg_frame_rate",
        "-of", "json",
        str(path),
    ]
    try:
        result = subprocess.run(
            command,
            shell=False,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=_PROBE_TIMEOUT_SECONDS,
            env={"PATH": str(pathlib.Path(binary).parent), "LANG": "C", "LC_ALL": "C"},
        )
    except (OSError, subprocess.TimeoutExpired):
        return VideoTechnicalMetadata(metadata_status="probe_failed")

    if result.returncode != 0 or len(result.stdout) > _MAX_PROBE_OUTPUT_BYTES:
        return VideoTechnicalMetadata(metadata_status="probe_failed")
    try:
        payload: Any = json.loads(result.stdout)
        if not isinstance(payload, dict):
            return VideoTechnicalMetadata(metadata_status="probe_failed")
        streams = payload.get("streams", [])
        if not isinstance(streams, list) or not all(
            isinstance(item, dict) for item in streams
        ):
            return VideoTechnicalMetadata(metadata_status="probe_failed")
        video = next(
            (item for item in streams if item.get("codec_type") == "video"),
            None,
        )
        if video is None:
            return VideoTechnicalMetadata(metadata_status="probe_failed")

        format_data = payload.get("format", {})
        if not isinstance(format_data, dict):
            return VideoTechnicalMetadata(metadata_status="probe_failed")

        # FFprobe output is untrusted parser input. Reject missing, non-finite,
        # or implausible core values rather than reporting misleading metadata.
        duration = float(format_data["duration"])
        width = int(video["width"])
        height = int(video["height"])
        numerator, separator, denominator = str(video["avg_frame_rate"]).partition("/")
        if not separator:
            return VideoTechnicalMetadata(metadata_status="probe_failed")
        numerator_value = float(numerator)
        denominator_value = float(denominator)
        if denominator_value <= 0:
            return VideoTechnicalMetadata(metadata_status="probe_failed")
        fps = numerator_value / denominator_value
        if (
            not math.isfinite(duration)
            or duration <= 0
            or duration > 86_400
            or width <= 0
            or height <= 0
            or width > 16_384
            or height > 16_384
            or not math.isfinite(fps)
            or fps <= 0
            or fps > 240
        ):
            return VideoTechnicalMetadata(metadata_status="probe_failed")

        has_audio = any(item.get("codec_type") == "audio" for item in streams)
        codec = video.get("codec_name")
        if codec is not None and (not isinstance(codec, str) or len(codec) > 64):
            return VideoTechnicalMetadata(metadata_status="probe_failed")
        return VideoTechnicalMetadata(
            duration_seconds=duration,
            width=width,
            height=height,
            frame_rate=round(fps, 3),
            codec=codec,
            has_audio=has_audio,
            metadata_status="available",
        )
    except (TypeError, ValueError, KeyError, ZeroDivisionError, json.JSONDecodeError):
        return VideoTechnicalMetadata(metadata_status="probe_failed")


def build_generation_prompt(
    *,
    style_summary: str,
    beats: list[dict[str, Any]],
    duration_seconds: int,
    aspect_ratio: str,
    brand_name: str | None = None,
    colors: list[str] | None = None,
    typography: str | None = None,
    sound_design: str | None = None,
    final_frame: str | None = None,
) -> str:
    """Build a structured prompt from analysis facts, not source expressions."""
    palette = ", ".join(colors or []) or "derive a coherent original palette from the analysis"
    beat_lines = []
    for index, beat in enumerate(beats, start=1):
        start = beat.get("start_seconds", "?")
        end = beat.get("end_seconds", "?")
        description = str(beat.get("generation_instruction", "Create an original visual beat."))[:1200]
        transition = str(beat.get("transition_to_next", "clean cinematic cut"))[:240]
        beat_lines.append(f"Beat {index} ({start}s–{end}s): {description} Transition: {transition}.")
    beats_text = "\n".join(beat_lines) or "Create a concise original sequence with a clear hook, development, and resolved ending."
    brand_line = f"Use the brand name {brand_name} only where appropriate; do not invent a logo." if brand_name else "Do not add unprovided brand marks."
    return (
        f"Create an original {duration_seconds}-second video in {aspect_ratio} aspect ratio.\n"
        f"Style: {style_summary[:1000]}\n"
        f"Palette: {palette}.\n"
        f"Typography: {typography or 'Use one consistent, legible modern sans-serif family; preserve exact supplied copy.'}\n"
        f"{brand_line}\n"
        f"Timeline:\n{beats_text}\n"
        f"Sound design: {sound_design or 'Use restrained, beat-synchronized original music and subtle transition effects.'}\n"
        f"Final frame: {final_frame or 'End on a clean, readable frame with a deliberate visual hold.'}\n"
        "Recreate visual techniques and pacing only. Do not reproduce protected logos, text, characters, footage, or distinctive copyrighted compositions."
    )
