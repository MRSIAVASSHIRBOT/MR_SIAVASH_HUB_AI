from __future__ import annotations

import hashlib
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest

import mrhub.video_intelligence.render_preflight as render_preflight
from mrhub.video_intelligence.timeline import VideoTimeline
from mrhub.video_intelligence.timeline_drafts import VideoTimelineDraftRepository


OWNER = "owner-a"
DRAFT_ID = UUID("11111111-1111-4111-8111-111111111111")
ANALYSIS_ID = UUID("22222222-2222-4222-8222-222222222222")
ASSET_ID = UUID("33333333-3333-4333-8333-333333333333")


def _timeline() -> VideoTimeline:
    return VideoTimeline.model_validate(
        {
            "schema_version": "1.0",
            "output_aspect_ratio": "9:16",
            "requested_duration_seconds": 3,
            "actual_duration_seconds": 3.0,
            "duration_shortfall_seconds": 0.0,
            "video_track": [
                {
                    "clip_id": "clip-1",
                    "source_asset_id": str(ASSET_ID),
                    "source_scene_index": 0,
                    "source_start_seconds": 0.0,
                    "source_end_seconds": 3.0,
                    "timeline_start_seconds": 0.0,
                    "timeline_end_seconds": 3.0,
                }
            ],
            "audio_analysis_status": "not_requested",
            "audio_render_status": "not_implemented",
            "timeline_status": "validated_cut_only",
            "render_status": "not_implemented",
        }
    )


def _install_fakes(monkeypatch, tmp_path: Path, *, digest_override=None, create_file=True):
    timeline = _timeline()
    canonical = VideoTimelineDraftRepository._canonical_renderer_timeline(timeline)
    digest = digest_override or hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    storage_key = str(ASSET_ID) + ".mp4"
    source_path = tmp_path / storage_key
    content = b"bounded-source-video"
    if create_file:
        source_path.write_bytes(content)
    draft = {
        "draft_id": str(DRAFT_ID),
        "analysis_id": str(ANALYSIS_ID),
        "asset_id": str(ASSET_ID),
        "version": 2,
        "renderer_timeline": timeline.model_dump(mode="json", exclude_none=True),
        "renderer_timeline_sha256": digest,
    }
    analysis = {
        "status": "completed",
        "result": {
            "assets": [
                {
                    "asset_id": str(ASSET_ID),
                    "technical_metadata": {
                        "duration_seconds": 10.0,
                        "has_audio": False,
                    },
                }
            ]
        },
    }
    asset = {
        "asset_id": str(ASSET_ID),
        "media_type": "video/mp4",
        "processing_status": "stored",
        "storage_key": storage_key,
        "file_size": len(content),
    }

    class FakeDraftRepository:
        _canonical_renderer_timeline = staticmethod(
            VideoTimelineDraftRepository._canonical_renderer_timeline
        )

        def __init__(self, _database_path):
            pass

        def get(self, owner_user_id, draft_id):
            return draft if owner_user_id == OWNER and draft_id == DRAFT_ID else None

    class FakeAnalysisRepository:
        def __init__(self, _database_path):
            pass

        def get(self, owner_user_id, analysis_id):
            return analysis if owner_user_id == OWNER and analysis_id == ANALYSIS_ID else None

    class FakeMediaRepository:
        def __init__(self, _database_path):
            self.storage_root = tmp_path

        def get(self, owner_user_id, asset_id):
            return asset if owner_user_id == OWNER and asset_id == ASSET_ID else None

        def file_path(self, requested_key):
            assert requested_key == storage_key
            return source_path

    monkeypatch.setattr(render_preflight, "VideoTimelineDraftRepository", FakeDraftRepository)
    monkeypatch.setattr(render_preflight, "VideoAnalysisJobRepository", FakeAnalysisRepository)
    monkeypatch.setattr(render_preflight, "MediaAssetRepository", FakeMediaRepository)
    monkeypatch.setattr(render_preflight.shutil, "which", lambda name: "/usr/bin/" + name)
    monkeypatch.setattr(render_preflight.os, "access", lambda _path, _mode: True)
    monkeypatch.setattr(
        render_preflight.shutil,
        "disk_usage",
        lambda _path: SimpleNamespace(total=500_000_000, used=100_000_000, free=400_000_000),
    )
    return draft, source_path


def test_preflight_passes_for_prepared_owner_owned_sources_without_starting_work(tmp_path, monkeypatch):
    _install_fakes(monkeypatch, tmp_path)
    result = render_preflight.inspect_video_render_preflight(
        tmp_path / "hub.sqlite", OWNER, DRAFT_ID
    )
    assert result["ready"] is True
    assert result["execution"] == "not_started"
    assert result["state_changed"] is False
    assert result["provider_calls"] == 0
    assert result["remote_calls"] == 0
    assert result["source_count"] == 1
    assert result["source_bytes"] == len(b"bounded-source-video")
    assert {item["code"] for item in result["checks"]} >= {
        "timeline_integrity",
        "analysis_completed",
        "source_bounds",
        "source_files",
        "ffmpeg_available",
        "ffprobe_available",
        "output_storage",
    }


def test_preflight_fails_closed_for_tampered_timeline_and_missing_source(tmp_path, monkeypatch):
    _install_fakes(monkeypatch, tmp_path, digest_override="0" * 64, create_file=False)
    result = render_preflight.inspect_video_render_preflight(
        tmp_path / "hub.sqlite", OWNER, DRAFT_ID
    )
    statuses = {item["code"]: item["status"] for item in result["checks"]}
    assert result["ready"] is False
    assert statuses["timeline_integrity"] == "fail"
    assert statuses["source_files"] == "fail"


def test_preflight_requires_both_local_ffmpeg_tools(tmp_path, monkeypatch):
    _install_fakes(monkeypatch, tmp_path)
    monkeypatch.setattr(
        render_preflight.shutil,
        "which",
        lambda name: None if name == "ffmpeg" else "/usr/bin/ffprobe",
    )
    result = render_preflight.inspect_video_render_preflight(
        tmp_path / "hub.sqlite", OWNER, DRAFT_ID
    )
    statuses = {item["code"]: item["status"] for item in result["checks"]}
    assert result["ready"] is False
    assert statuses["ffmpeg_available"] == "fail"
    assert statuses["ffprobe_available"] == "pass"


def test_preflight_reports_low_disk_as_warning_without_claiming_failure(tmp_path, monkeypatch):
    _install_fakes(monkeypatch, tmp_path)
    monkeypatch.setattr(
        render_preflight.shutil,
        "disk_usage",
        lambda _path: SimpleNamespace(total=10_000, used=9_999, free=1),
    )
    result = render_preflight.inspect_video_render_preflight(
        tmp_path / "hub.sqlite", OWNER, DRAFT_ID
    )
    statuses = {item["code"]: item["status"] for item in result["checks"]}
    assert result["ready"] is True
    assert statuses["disk_space"] == "warning"
    assert result["warnings"] == ["disk_space"]


def test_preflight_does_not_disclose_another_owners_draft(tmp_path, monkeypatch):
    _install_fakes(monkeypatch, tmp_path)
    with pytest.raises(LookupError, match="video_render_draft_not_found"):
        render_preflight.inspect_video_render_preflight(
            tmp_path / "hub.sqlite", "owner-b", DRAFT_ID
        )
