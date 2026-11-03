"""Evidence-grounded local visual analysis over transient sampled frames."""

from __future__ import annotations

from collections.abc import Callable, Sequence

from pydantic import ValidationError

from mrhub.providers.base import ProviderError
from mrhub.providers.vision import (
    OllamaVisionProvider,
    VisionImage,
    VisionProvider,
    VisionRequest,
)
from mrhub.video_intelligence.frames import ExtractedVideoFrame
from mrhub.video_intelligence.visual_schemas import VisualAnalysisResult

VisionProviderFactory = Callable[..., VisionProvider]


def _analysis_prompt(timestamps: Sequence[float]) -> str:
    frame_lines = "\n".join(
        f"{index}: {timestamp:.3f} seconds"
        for index, timestamp in enumerate(timestamps, start=1)
    )
    return (
        "Analyze the supplied JPEG frames in their given order as evidence from one video. "
        "Describe only details that are visibly supported by the images. Do not identify "
        "real people, infer private traits, invent actions between frames, or claim audio "
        "content. Distinguish observation from uncertainty and use confidence conservatively. "
        "Do not reproduce logos, exact protected text, or distinctive copyrighted expression. "
        "Return only one JSON object with this exact shape: "
        '{"style_summary":"string","observations":[{"timestamp_seconds":0.0,'
        '"description":"string","shot_scale":"extreme_wide|wide|medium|close_up|extreme_close_up|unclear",'
        '"camera_movement":"static|pan|tilt|tracking|zoom|handheld|unclear",'
        '"composition":"string","lighting":"string","color_notes":["string"],"confidence":0.0}]}. '
        "Use only the supplied timestamp values, do not invent or interpolate timestamps, "
        "and include at least one observation. The frame index-to-timestamp mapping is:\n"
        f"{frame_lines}"
    )


def analyze_sampled_frames(
    frames: Sequence[ExtractedVideoFrame],
    *,
    enabled: bool,
    model: str | None,
    base_url: str,
    timeout_seconds: float,
    provider_factory: VisionProviderFactory = OllamaVisionProvider,
) -> dict[str, object]:
    """Analyze bounded transient frames locally; never fall back to a remote provider."""
    if not enabled:
        return {"status": "not_configured", "reason_code": "local_vision_disabled"}
    if not model or not model.strip():
        return {"status": "not_configured", "reason_code": "local_vision_model_missing"}
    if not frames:
        return {"status": "not_available", "reason_code": "no_sampled_frames"}

    try:
        provider = provider_factory(
            model=model,
            base_url=base_url,
            timeout_seconds=timeout_seconds,
        )
        request = VisionRequest(
            prompt=_analysis_prompt([frame.timestamp_seconds for frame in frames]),
            images=tuple(
                VisionImage(
                    timestamp_seconds=frame.timestamp_seconds,
                    jpeg_bytes=frame.jpeg_bytes,
                )
                for frame in frames
            ),
            max_output_tokens=1200,
        )
        response = provider.generate(request)
    except ProviderError as exc:
        return {"status": "unavailable", "reason_code": exc.code}
    except (TypeError, ValueError):
        return {"status": "invalid_input", "reason_code": "vision_input_rejected"}

    try:
        parsed = VisualAnalysisResult.model_validate_json(response.output_text)
    except (ValidationError, ValueError):
        return {"status": "invalid_response", "reason_code": "visual_output_invalid"}

    allowed_timestamps = {round(frame.timestamp_seconds, 3) for frame in frames}
    observed_timestamps = [
        round(item.timestamp_seconds, 3) for item in parsed.observations
    ]
    if (
        any(value not in allowed_timestamps for value in observed_timestamps)
        or observed_timestamps != sorted(observed_timestamps)
    ):
        return {"status": "invalid_response", "reason_code": "visual_timestamp_mismatch"}

    return {
        "status": "completed",
        "provider": response.provider,
        "model": response.model,
        "style_summary": parsed.style_summary,
        "observations": [
            item.model_dump(mode="json") for item in parsed.observations
        ],
    }
