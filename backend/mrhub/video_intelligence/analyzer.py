"""Internal composition of owner-scoped, bounded video analysis primitives."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from uuid import UUID

from mrhub.video_intelligence.frames import (
    ExtractedVideoFrame,
    FrameExtractionError,
    extract_video_frames,
)
from mrhub.video_intelligence.scenes import (
    SceneDetectionError,
    SceneDetectionResult,
    detect_scene_boundaries,
)
from mrhub.video_intelligence.schemas import VideoTechnicalMetadata
from mrhub.video_intelligence.service import probe_video


class VideoAssetAnalysisError(RuntimeError):
    """Raised when an owned video cannot be prepared for bounded analysis."""

    def __init__(self, reason_code: str) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code


class MediaAssetLookup(Protocol):
    """Narrow repository surface required by the internal analysis service."""

    def get(self, owner_user_id: str, asset_id: UUID) -> dict[str, object] | None: ...

    def file_path(self, storage_key: str) -> Path: ...


@dataclass(frozen=True, slots=True)
class AnalyzedVideoAsset:
    """Ephemeral analysis package; extracted frames are not persisted."""

    asset_id: UUID
    content_hash: str
    analyzed_duration_seconds: float
    metadata: VideoTechnicalMetadata
    frames: tuple[ExtractedVideoFrame, ...]
    scenes: SceneDetectionResult


class VideoAssetAnalyzer:
    """Resolve an owner's stored video and compose bounded local analyzers.

    This service is intended for a worker or another trusted internal caller.
    It is deliberately not wired into an HTTP route: FFmpeg analysis can be
    expensive and must run through the shared job engine.
    """

    MAX_DURATION_SECONDS = 60.0
    MAX_FRAMES = 12
    MAX_FRAME_WIDTH = 1280
    MAX_SCENE_CHANGES = 24

    def __init__(
        self,
        database_path: Path,
        *,
        repository: MediaAssetLookup | None = None,
    ) -> None:
        if repository is None:
            from mrhub.media.repository import MediaAssetRepository

            repository = MediaAssetRepository(database_path)
        self.repository = repository

    def analyze(
        self,
        owner_user_id: str,
        asset_id: UUID,
        *,
        duration_seconds: float = MAX_DURATION_SECONDS,
        max_frames: int = MAX_FRAMES,
        scene_threshold: float = 0.30,
        max_scene_changes: int = MAX_SCENE_CHANGES,
    ) -> AnalyzedVideoAsset:
        """Probe an owned video, then extract bounded frames and scene timestamps."""
        if (
            not math.isfinite(duration_seconds)
            or not 0.1 <= duration_seconds <= self.MAX_DURATION_SECONDS
        ):
            raise ValueError("duration_seconds must be finite and between 0.1 and 60")
        if (
            isinstance(max_frames, bool)
            or not isinstance(max_frames, int)
            or not 1 <= max_frames <= self.MAX_FRAMES
        ):
            raise ValueError("max_frames must be an integer between 1 and 12")
        if not math.isfinite(scene_threshold) or not 0.05 <= scene_threshold <= 0.95:
            raise ValueError("scene_threshold must be between 0.05 and 0.95")
        if (
            isinstance(max_scene_changes, bool)
            or not isinstance(max_scene_changes, int)
            or not 1 <= max_scene_changes <= self.MAX_SCENE_CHANGES
        ):
            raise ValueError("max_scene_changes must be an integer between 1 and 24")

        asset = self.repository.get(owner_user_id, asset_id)
        if asset is None:
            raise VideoAssetAnalysisError("asset_not_found")
        if asset.get("media_type") not in {"video/mp4", "video/quicktime"}:
            raise VideoAssetAnalysisError("unsupported_media_type")

        try:
            path = self.repository.file_path(str(asset["storage_key"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise VideoAssetAnalysisError("asset_storage_reference_invalid") from exc
        if not path.is_file():
            raise VideoAssetAnalysisError("asset_file_missing")

        metadata = probe_video(path)
        if metadata.metadata_status != "available":
            raise VideoAssetAnalysisError("video_metadata_unavailable")
        source_duration = metadata.duration_seconds
        if source_duration is None or not math.isfinite(source_duration) or source_duration <= 0:
            raise VideoAssetAnalysisError("video_duration_invalid")
        analyzed_duration = min(duration_seconds, source_duration)
        if analyzed_duration < 0.1:
            raise VideoAssetAnalysisError("video_duration_invalid")

        try:
            frames = extract_video_frames(
                path,
                duration_seconds=analyzed_duration,
                max_frames=max_frames,
                max_width=self.MAX_FRAME_WIDTH,
            )
        except FrameExtractionError as exc:
            raise VideoAssetAnalysisError(f"frame_{exc.reason_code}") from exc

        try:
            scenes = detect_scene_boundaries(
                path,
                duration_seconds=analyzed_duration,
                threshold=scene_threshold,
                max_scene_changes=max_scene_changes,
            )
        except SceneDetectionError as exc:
            raise VideoAssetAnalysisError(f"scene_{exc.reason_code}") from exc

        content_hash = asset.get("content_hash")
        return AnalyzedVideoAsset(
            asset_id=asset_id,
            content_hash=content_hash if isinstance(content_hash, str) else "",
            analyzed_duration_seconds=round(analyzed_duration, 3),
            metadata=metadata,
            frames=tuple(frames),
            scenes=scenes,
        )
