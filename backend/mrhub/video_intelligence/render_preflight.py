"""Read-only readiness checks for an owner-scoped local video render."""

from __future__ import annotations

import hashlib
import hmac
import os
import shutil
from pathlib import Path
from uuid import UUID

from mrhub.media.repository import MAX_OUTPUT_BYTES, MediaAssetRepository
from mrhub.video_intelligence.jobs import VideoAnalysisJobRepository
from mrhub.video_intelligence.timeline import VideoTimeline
from mrhub.video_intelligence.timeline_drafts import (
    VideoTimelineDraftRepository,
    validate_renderer_timeline_source_bounds,
)

MAX_PREFLIGHT_SOURCE_HASH_BYTES = 512 * 1024 * 1024


def _check(code: str, status: str, detail: str) -> dict[str, str]:
    return {"code": code, "status": status, "detail": detail}


def inspect_video_render_preflight(
    database_path: Path, owner_user_id: str, draft_id: UUID
) -> dict[str, object]:
    """Inspect local render prerequisites without creating jobs or invoking FFmpeg."""
    draft = VideoTimelineDraftRepository(database_path).get(owner_user_id, draft_id)
    if draft is None:
        raise LookupError("video_render_draft_not_found")

    checks: list[dict[str, str]] = []
    timeline: VideoTimeline | None = None
    renderer_data = draft.get("renderer_timeline")
    renderer_digest = draft.get("renderer_timeline_sha256")
    try:
        if not isinstance(renderer_data, dict) or not isinstance(renderer_digest, str):
            raise TypeError("renderer_timeline_not_saved")
        timeline = VideoTimeline.model_validate(renderer_data)
        canonical = VideoTimelineDraftRepository._canonical_renderer_timeline(timeline)
        actual_digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        if not hmac.compare_digest(actual_digest, renderer_digest):
            raise ValueError("renderer_timeline_checksum_mismatch")
        checks.append(
            _check(
                "timeline_integrity",
                "pass",
                "Saved renderer timeline and SHA-256 checksum match.",
            )
        )
    except (TypeError, ValueError):
        checks.append(
            _check(
                "timeline_integrity",
                "fail",
                "Prepare and save a valid renderer timeline before submitting a render.",
            )
        )

    analysis = None
    analysis_id: UUID | None = None
    try:
        analysis_id = UUID(str(draft.get("analysis_id")))
        analysis = VideoAnalysisJobRepository(database_path).get(
            owner_user_id, analysis_id
        )
    except (TypeError, ValueError):
        analysis = None

    analysis_ready = (
        analysis is not None
        and analysis.get("status") == "completed"
        and isinstance(analysis.get("result"), dict)
    )
    checks.append(
        _check(
            "analysis_completed",
            "pass" if analysis_ready else "fail",
            "The source analysis is completed and belongs to this owner."
            if analysis_ready
            else "A completed owner-owned source analysis is required.",
        )
    )

    source_count = 0
    source_bytes = 0
    source_files_ready = False
    if timeline is not None and analysis_ready:
        assets = analysis["result"].get("assets")
        source_ids = {clip.source_asset_id for clip in timeline.video_track}
        source_count = len(source_ids)
        allowed_ids = {
            str(item["asset_id"])
            for item in assets
            if isinstance(item, dict) and item.get("asset_id")
        } if isinstance(assets, list) else set()
        references_valid = (
            1 <= source_count <= 125
            and source_ids.issubset(allowed_ids)
            and str(draft.get("asset_id")) in source_ids
        )
        source_assets: list[dict[str, object]] = []
        try:
            if not references_valid or not isinstance(assets, list):
                raise ValueError("render_source_ownership_invalid")
            validate_renderer_timeline_source_bounds(timeline, assets)
            checks.append(
                _check(
                    "source_bounds",
                    "pass",
                    "Every clip fits the source durations recorded by the completed analysis.",
                )
            )
            media = MediaAssetRepository(database_path)
            for source_id in sorted(source_ids):
                asset_id = UUID(source_id)
                asset = media.get(owner_user_id, asset_id)
                if (
                    asset is None
                    or asset.get("media_type") not in {"video/mp4", "video/quicktime"}
                    or asset.get("processing_status") not in {"stored", "processed"}
                ):
                    raise ValueError("render_source_not_ready")
                storage_key = asset.get("storage_key")
                recorded_size = asset.get("file_size")
                if (
                    not isinstance(storage_key, str)
                    or isinstance(recorded_size, bool)
                    or not isinstance(recorded_size, int)
                    or not 0 < recorded_size <= MAX_OUTPUT_BYTES
                ):
                    raise ValueError("render_source_metadata_invalid")
                path = media.file_path(storage_key)
                if not path.is_file():
                    raise ValueError("render_source_file_missing")
                actual_size = path.stat().st_size
                if actual_size != recorded_size:
                    raise ValueError("render_source_size_mismatch")
                source_bytes += actual_size
                source_assets.append(asset)
            source_files_ready = True
            checks.append(
                _check(
                    "source_files",
                    "pass",
                    "All referenced owner-owned source files exist and match their recorded sizes.",
                )
            )
            if source_bytes > MAX_PREFLIGHT_SOURCE_HASH_BYTES:
                checks.append(
                    _check(
                        "source_integrity",
                        "warning",
                        "The preflight checksum budget was exceeded; "
                        "the worker will verify every source before rendering.",
                    )
                )
            elif all(media.verify_file_integrity(asset) for asset in source_assets):
                checks.append(
                    _check(
                        "source_integrity",
                        "pass",
                        "Every source file matches its recorded SHA-256 content hash.",
                    )
                )
            else:
                checks.append(
                    _check(
                        "source_integrity",
                        "fail",
                        "One or more source files do not match their "
                        "recorded SHA-256 content hash.",
                    )
                )
        except (OSError, TypeError, ValueError):
            checks.append(
                _check(
                    "source_files",
                    "fail",
                    "One or more source files are missing, changed, unsupported, or not ready.",
                )
            )
            checks.append(
                _check(
                    "source_integrity",
                    "fail",
                    "Source file integrity could not be verified.",
                )
            )
            if not any(item["code"] == "source_bounds" for item in checks):
                checks.append(
                    _check(
                        "source_bounds",
                        "fail",
                        "Source ownership, duration bounds, or timeline references are invalid.",
                    )
                )
    else:
        checks.extend(
            [
                _check(
                    "source_bounds",
                    "fail",
                    "A valid saved timeline and completed analysis are required.",
                ),
                _check(
                    "source_files",
                    "fail",
                    "Source files cannot be checked until the analysis is complete.",
                ),
                _check(
                    "source_integrity",
                    "fail",
                    "Source files cannot be verified until the analysis is complete.",
                ),
            ]
        )

    ffmpeg_available = shutil.which("ffmpeg") is not None
    ffprobe_available = shutil.which("ffprobe") is not None
    checks.append(
        _check(
            "ffmpeg_available",
            "pass" if ffmpeg_available else "fail",
            "FFmpeg is available to the local Hub process."
            if ffmpeg_available
            else "FFmpeg is not available on the local Hub process PATH.",
        )
    )
    checks.append(
        _check(
            "ffprobe_available",
            "pass" if ffprobe_available else "fail",
            "FFprobe is available to the local Hub process."
            if ffprobe_available
            else "FFprobe is not available on the local Hub process PATH.",
        )
    )

    storage_ready = False
    free_bytes: int | None = None
    try:
        media_for_storage = MediaAssetRepository(database_path)
        storage_root = media_for_storage.storage_root
        storage_ready = storage_root.is_dir() and os.access(storage_root, os.W_OK)
        if storage_ready:
            free_bytes = shutil.disk_usage(storage_root).free
    except OSError:
        storage_ready = False
    checks.append(
        _check(
            "output_storage",
            "pass" if storage_ready else "fail",
            "The private media output directory exists and is writable."
            if storage_ready
            else "The private media output directory is unavailable or not writable.",
        )
    )
    checks.append(
        _check(
            "disk_space",
            "pass" if free_bytes is not None and free_bytes >= MAX_OUTPUT_BYTES
            else "warning",
            "At least the maximum bounded output size is available."
            if free_bytes is not None and free_bytes >= MAX_OUTPUT_BYTES
            else "Free space is below the 100 MB output cap or could not be measured; the worker will recheck during execution.",
        )
    )

    ready = all(item["status"] != "fail" for item in checks)
    warnings = [item["code"] for item in checks if item["status"] == "warning"]
    return {
        "draft_id": str(draft_id),
        "draft_version": draft.get("version"),
        "ready": ready,
        "checks": checks,
        "warnings": warnings,
        "source_count": source_count,
        "source_bytes": source_bytes if source_files_ready else None,
        "duration_seconds": (
            round(timeline.actual_duration_seconds, 3) if timeline is not None else None
        ),
        "aspect_ratio": timeline.output_aspect_ratio if timeline is not None else None,
        "max_output_bytes": MAX_OUTPUT_BYTES,
        "execution": "not_started",
        "state_changed": False,
        "provider_calls": 0,
        "remote_calls": 0,
        "note": (
            "This is a read-only snapshot. The worker rechecks ownership, file access, "
            "and active media leases immediately before rendering."
        ),
    }
