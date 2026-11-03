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

from mrhub.video_intelligence.schemas import BrandIdentity, VideoTechnicalMetadata
from mrhub.video_intelligence.visual_schemas import VisualAnalysisResult

_PROBE_TIMEOUT_SECONDS = 12
_MAX_PROBE_OUTPUT_BYTES = 64 * 1024
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



def build_prompt_from_visual_analysis(
    *,
    visual_analysis: VisualAnalysisResult,
    source_duration_seconds: float,
    duration_seconds: int,
    aspect_ratio: str,
    brand: BrandIdentity | None = None,
    custom_changes: dict[str, str] | None = None,
    sound_design: str | None = None,
    final_frame: str | None = None,
) -> str:
    """Turn validated frame observations into an original, bounded edit prompt.

    Observation timestamps are mapped proportionally onto the requested output
    duration. The function describes high-level visual techniques only and does
    not attempt to reproduce source subjects, exact layouts, logos, or text.
    """
    if not math.isfinite(source_duration_seconds) or source_duration_seconds <= 0:
        raise ValueError("source_duration_seconds must be positive and finite")
    if not 3 <= duration_seconds <= 60:
        raise ValueError("duration_seconds must be between 3 and 60")
    if not visual_analysis.observations:
        raise ValueError("At least one visual observation is required")

    mapped: list[tuple[float, Any]] = []
    for observation in visual_analysis.observations:
        position = min(
            float(duration_seconds),
            max(0.0, observation.timestamp_seconds / source_duration_seconds * duration_seconds),
        )
        mapped.append((round(position, 3), observation))
    mapped.sort(key=lambda item: item[0])

    # Collapse timestamp collisions after proportional mapping. The highest
    # confidence observation wins; ties preserve the earlier source ordering.
    unique: list[tuple[float, Any]] = []
    for position, observation in mapped:
        if unique and position <= unique[-1][0]:
            if observation.confidence > unique[-1][1].confidence:
                unique[-1] = (unique[-1][0], observation)
            continue
        unique.append((position, observation))

    beats: list[dict[str, Any]] = []
    for index, (position, observation) in enumerate(unique):
        start = 0.0 if index == 0 else position
        end = unique[index + 1][0] if index + 1 < len(unique) else float(duration_seconds)
        if end <= start:
            continue
        details = [
            observation.description,
            f"shot scale: {observation.shot_scale}",
            f"camera movement: {observation.camera_movement}",
        ]
        if observation.composition:
            details.append(f"composition: {observation.composition}")
        if observation.lighting:
            details.append(f"lighting: {observation.lighting}")
        if observation.color_notes:
            details.append("color direction: " + ", ".join(observation.color_notes))
        details.append(
            "Translate these observations into an original scene; do not copy the source subject, "
            "exact framing, protected text, logos, or distinctive composition."
        )
        beats.append({
            "start_seconds": round(start, 3),
            "end_seconds": round(end, 3),
            "generation_instruction": "; ".join(details)[:1200],
            "transition_to_next": "clean cinematic cut with rhythm appropriate to the scene",
        })

    if not beats:
        raise ValueError("No valid timeline intervals could be composed")

    brand_colors = brand.colors if brand else []
    typography = (
        ", ".join(brand.font_preferences)
        if brand and brand.font_preferences
        else None
    )
    prompt = build_generation_prompt(
        style_summary=visual_analysis.style_summary,
        beats=beats,
        duration_seconds=duration_seconds,
        aspect_ratio=aspect_ratio,
        brand_name=brand.brand_name if brand else None,
        colors=brand_colors,
        typography=typography,
        sound_design=sound_design,
        final_frame=final_frame,
    )
    if brand and brand.tone:
        prompt += f"\nBrand tone: {brand.tone[:240]}."
    if brand and brand.handle:
        prompt += f"\nBrand handle, only if a closing credit is requested: {brand.handle[:80]}."
    if custom_changes:
        changes = [
            f"- {str(key)[:40]}: {str(value)[:240]}"
            for key, value in list(custom_changes.items())[:12]
        ]
        if changes:
            prompt += "\nAdditional user constraints:\n" + "\n".join(changes)
    prompt += (
        "\nEvidence note: this scenario is derived only from validated visual observations "
        "at sampled timestamps. Audio was not analyzed; do not infer dialogue, lyrics, or "
        "sound events from the visual reference."
    )
    return prompt
