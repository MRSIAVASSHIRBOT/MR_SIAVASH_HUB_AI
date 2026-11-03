"""Bounded, local-only uniform keyframe extraction for owned video assets."""

from __future__ import annotations

import pathlib
import shutil
import subprocess
import tempfile
from dataclasses import dataclass

_MAX_SOURCE_BYTES = 25_000_000
_MAX_DURATION_SECONDS = 60.0
_MAX_FRAMES = 12
_MAX_FRAME_BYTES = 1_500_000
_MAX_TOTAL_FRAME_BYTES = 12_000_000
_MAX_FRAME_WIDTH = 1280
_EXTRACTION_TIMEOUT_SECONDS = 30


class FrameExtractionError(RuntimeError):
    """Raised when a bounded keyframe extraction cannot complete safely."""

    def __init__(self, reason_code: str) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code


@dataclass(frozen=True, slots=True)
class ExtractedVideoFrame:
    """A sampled JPEG frame and its approximate source timestamp."""

    timestamp_seconds: float
    jpeg_bytes: bytes


def extract_video_frames(
    path: pathlib.Path,
    *,
    duration_seconds: float,
    max_frames: int = 12,
    max_width: int = 1280,
) -> list[ExtractedVideoFrame]:
    """Extract uniformly sampled JPEG frames from a trusted local asset path.

    The caller must resolve `path` through the authenticated media repository.
    Remote protocols, shell expansion, unbounded duration, and unbounded output
    are deliberately excluded.
    """
    if not 0.1 <= duration_seconds <= _MAX_DURATION_SECONDS:
        raise ValueError("duration_seconds must be between 0.1 and 60 seconds")
    if not 1 <= max_frames <= _MAX_FRAMES:
        raise ValueError("max_frames must be between 1 and 12")
    if not 160 <= max_width <= _MAX_FRAME_WIDTH:
        raise ValueError("max_width must be between 160 and 1280")
    if not path.is_file():
        raise FrameExtractionError("source_missing")
    try:
        source = path.resolve(strict=True)
        if source.stat().st_size <= 0 or source.stat().st_size > _MAX_SOURCE_BYTES:
            raise FrameExtractionError("source_size_out_of_range")
    except OSError as exc:
        raise FrameExtractionError("source_unavailable") from exc

    binary = shutil.which("ffmpeg")
    if binary is None:
        raise FrameExtractionError("ffmpeg_unavailable")

    # Cap the sampling rate as well as the frame count so short clips do not
    # trigger excessive decode work.
    sampling_rate = min(max_frames / duration_seconds, 2.0)
    filter_expression = (
        f"fps={sampling_rate:.6f},scale=w='min({max_width},iw)':h=-2"
    )

    try:
        with tempfile.TemporaryDirectory(prefix="mrhub-video-frames-") as directory:
            output_pattern = str(pathlib.Path(directory) / "frame-%02d.jpg")
            command = [
                binary,
                "-nostdin",
                "-hide_banner",
                "-loglevel", "error",
                "-protocol_whitelist", "file,pipe",
                "-i", str(source),
                "-t", f"{duration_seconds:.3f}",
                "-map", "0:v:0",
                "-an",
                "-sn",
                "-dn",
                "-vf", filter_expression,
                "-frames:v", str(max_frames),
                "-threads", "1",
                "-q:v", "4",
                "-f", "image2",
                "-y",
                output_pattern,
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
                    capture_output=True,
                    timeout=_EXTRACTION_TIMEOUT_SECONDS,
                    env=environment,
                )
            except subprocess.TimeoutExpired as exc:
                raise FrameExtractionError("extraction_timeout") from exc
            except OSError as exc:
                raise FrameExtractionError("ffmpeg_execution_failed") from exc

            if result.returncode != 0:
                raise FrameExtractionError("extraction_failed")

            frame_paths = sorted(pathlib.Path(directory).glob("frame-*.jpg"))
            if not frame_paths or len(frame_paths) > max_frames:
                raise FrameExtractionError("no_frames_extracted")

            frames: list[ExtractedVideoFrame] = []
            total_bytes = 0
            for index, frame_path in enumerate(frame_paths):
                try:
                    frame_bytes = frame_path.read_bytes()
                except OSError as exc:
                    raise FrameExtractionError("frame_read_failed") from exc
                if not frame_bytes or len(frame_bytes) > _MAX_FRAME_BYTES:
                    raise FrameExtractionError("frame_size_out_of_range")
                total_bytes += len(frame_bytes)
                if total_bytes > _MAX_TOTAL_FRAME_BYTES:
                    raise FrameExtractionError("total_frame_size_exceeded")
                timestamp = min(index / sampling_rate, duration_seconds)
                frames.append(
                    ExtractedVideoFrame(
                        timestamp_seconds=round(timestamp, 3),
                        jpeg_bytes=frame_bytes,
                    )
                )
            return frames
    except FrameExtractionError:
        raise
    except OSError as exc:
        raise FrameExtractionError("temporary_storage_failed") from exc
