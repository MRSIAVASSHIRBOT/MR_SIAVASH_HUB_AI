"""Bounded, local-only FFmpeg scene-boundary timestamp detection."""

from __future__ import annotations

import csv
import math
import pathlib
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from fractions import Fraction

_MAX_SOURCE_BYTES = 25_000_000
_MAX_DURATION_SECONDS = 60.0
_MAX_SCENE_CHANGES = 24
_MAX_FRAME_WIDTH = 640
_MAX_FRAMEHASH_OUTPUT_BYTES = 16_384
_DETECTION_TIMEOUT_SECONDS = 30
_MAX_DECODED_PIXELS = 33_554_432


class SceneDetectionError(RuntimeError):
    """Raised when bounded scene-boundary detection cannot complete safely."""

    def __init__(self, reason_code: str) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code


@dataclass(frozen=True, slots=True)
class SceneDetectionResult:
    """Scene start timestamps; the first boundary is always the clip start."""

    scene_start_times: tuple[float, ...]
    truncated: bool = False

    @property
    def scene_count(self) -> int:
        """Return the number of represented scenes, including the opening scene."""
        return len(self.scene_start_times)


def _parse_framehash_timestamps(output: bytes) -> list[float]:
    """Parse FFmpeg framehash PTS values using its declared stream time base."""
    try:
        lines = output.decode("ascii").splitlines()
    except UnicodeDecodeError as exc:
        raise SceneDetectionError("scene_output_invalid") from exc

    time_base: Fraction | None = None
    timestamps: list[float] = []
    for line in lines:
        if line.startswith("#tb 0:"):
            try:
                time_base = Fraction(line.split(":", 1)[1].strip())
            except (ValueError, ZeroDivisionError) as exc:
                raise SceneDetectionError("scene_time_base_invalid") from exc
            if time_base <= 0:
                raise SceneDetectionError("scene_time_base_invalid")
            continue
        if not line or line.startswith("#"):
            continue
        try:
            fields = next(csv.reader([line]))
            if len(fields) != 6 or int(fields[0].strip()) != 0:
                raise ValueError("unexpected framehash row")
            pts = int(fields[2].strip())
            if time_base is None:
                raise ValueError("framehash time base is missing")
        except (csv.Error, ValueError, StopIteration) as exc:
            raise SceneDetectionError("scene_output_invalid") from exc
        timestamp = float(pts * time_base)
        if not math.isfinite(timestamp) or timestamp < 0:
            raise SceneDetectionError("scene_timestamp_invalid")
        timestamps.append(timestamp)
    if time_base is None:
        raise SceneDetectionError("scene_time_base_invalid")
    return timestamps


def detect_scene_boundaries(
    path: pathlib.Path,
    *,
    duration_seconds: float,
    threshold: float = 0.30,
    max_scene_changes: int = 24,
) -> SceneDetectionResult:
    """Detect visual cut timestamps in a trusted local video asset.

    The caller must resolve the path through the authenticated media repository.
    Only timestamps are returned; no source frames or copied visual expression are
    retained. This is deterministic FFmpeg scene-score detection, not semantic
    scene understanding.
    """
    if (
        not math.isfinite(duration_seconds)
        or not 0.1 <= duration_seconds <= _MAX_DURATION_SECONDS
    ):
        raise ValueError("duration_seconds must be finite and between 0.1 and 60")
    if not math.isfinite(threshold) or not 0.05 <= threshold <= 0.95:
        raise ValueError("threshold must be between 0.05 and 0.95")
    if (
        isinstance(max_scene_changes, bool)
        or not isinstance(max_scene_changes, int)
        or not 1 <= max_scene_changes <= _MAX_SCENE_CHANGES
    ):
        raise ValueError("max_scene_changes must be between 1 and 24")
    if not path.is_file():
        raise SceneDetectionError("source_missing")
    try:
        source = path.resolve(strict=True)
        source_size = source.stat().st_size
        if source_size <= 0 or source_size > _MAX_SOURCE_BYTES:
            raise SceneDetectionError("source_size_out_of_range")
    except OSError as exc:
        raise SceneDetectionError("source_unavailable") from exc

    binary = shutil.which("ffmpeg")
    if binary is None:
        raise SceneDetectionError("ffmpeg_unavailable")

    filter_expression = (
        f"select='gt(scene,{threshold:.3f})',"
        f"scale=w='min({_MAX_FRAME_WIDTH},iw)':"
        f"h='min({_MAX_FRAME_WIDTH},ih)':"
        "force_original_aspect_ratio=decrease"
    )
    # Ask for one extra boundary so hitting the public cap is distinguishable
    # from a complete result. framehash emits bounded timestamp rows, not images.
    output_frame_limit = max_scene_changes + 1

    with tempfile.TemporaryDirectory(prefix="mrhub-video-scenes-") as directory:
        command = [
            binary,
            "-nostdin",
            "-hide_banner",
            "-loglevel", "error",
            "-protocol_whitelist", "file,pipe",
            "-max_pixels", str(_MAX_DECODED_PIXELS),
            "-i", str(source),
            "-t", f"{duration_seconds:.3f}",
            "-map", "0:v:0",
            "-an",
            "-sn",
            "-dn",
            "-vf", filter_expression,
            "-frames:v", str(output_frame_limit),
            "-threads", "1",
            "-f", "framehash",
            "-",
        ]
        environment = {
            "PATH": str(pathlib.Path(binary).parent),
            "HOME": directory,
            "TMPDIR": directory,
            "LANG": "C",
            "LC_ALL": "C",
        }
        try:
            result = subprocess.run(
                command,
                shell=False,
                check=False,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                timeout=_DETECTION_TIMEOUT_SECONDS,
                env=environment,
            )
        except subprocess.TimeoutExpired as exc:
            raise SceneDetectionError("detection_timeout") from exc
        except OSError as exc:
            raise SceneDetectionError("ffmpeg_execution_failed") from exc

    if result.returncode != 0:
        raise SceneDetectionError("detection_failed")
    if len(result.stdout) > _MAX_FRAMEHASH_OUTPUT_BYTES:
        raise SceneDetectionError("scene_output_too_large")

    detected = _parse_framehash_timestamps(result.stdout)
    valid_timestamps: list[float] = []
    for timestamp in detected:
        if timestamp > duration_seconds + 0.25:
            raise SceneDetectionError("scene_timestamp_out_of_range")
        if valid_timestamps and timestamp < valid_timestamps[-1] - 0.001:
            raise SceneDetectionError("scene_timestamps_not_monotonic")
        if timestamp > 0 and (
            not valid_timestamps or timestamp - valid_timestamps[-1] > 0.001
        ):
            valid_timestamps.append(round(timestamp, 3))

    truncated = len(valid_timestamps) > max_scene_changes
    retained = valid_timestamps[:max_scene_changes]
    return SceneDetectionResult(
        scene_start_times=(0.0, *retained),
        truncated=truncated,
    )
