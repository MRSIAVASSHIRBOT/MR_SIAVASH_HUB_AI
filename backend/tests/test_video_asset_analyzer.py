import uuid

import pytest

from mrhub.video_intelligence.analyzer import (
    VideoAssetAnalysisError,
    VideoAssetAnalyzer,
)
from mrhub.video_intelligence.frames import ExtractedVideoFrame, FrameExtractionError
from mrhub.video_intelligence.scenes import SceneDetectionError, SceneDetectionResult
from mrhub.video_intelligence.schemas import VideoTechnicalMetadata

ASSET_ID = uuid.UUID("9c4d0a4e-7ef3-4ea5-9463-bc03b3e9a960")


class FakeMediaRepository:
    def __init__(self, path, record=None):
        self.path = path
        self.record = record or {
            "asset_id": str(ASSET_ID),
            "media_type": "video/mp4",
            "storage_key": "owned-video.mp4",
            "content_hash": "a" * 64,
        }
        self.lookups = []

    def get(self, owner_user_id, asset_id):
        self.lookups.append((owner_user_id, asset_id))
        return self.record

    def file_path(self, storage_key):
        assert storage_key == "owned-video.mp4"
        return self.path


def make_analyzer(tmp_path, record=None):
    path = tmp_path / "owned-video.mp4"
    path.write_bytes(b"video fixture")
    repository = FakeMediaRepository(path, record)
    return VideoAssetAnalyzer(tmp_path / "database.sqlite3", repository=repository), repository, path


def test_analyzer_composes_owned_probe_frames_and_scenes_with_one_bounded_duration(
    tmp_path, monkeypatch
):
    analyzer, repository, path = make_analyzer(tmp_path)
    calls = {}
    metadata = VideoTechnicalMetadata(
        duration_seconds=7.5,
        width=1920,
        height=1080,
        frame_rate=29.97,
        codec="h264",
        has_audio=True,
        metadata_status="available",
    )
    frame = ExtractedVideoFrame(timestamp_seconds=0.5, jpeg_bytes=b"jpeg")
    scenes = SceneDetectionResult(scene_start_times=(0.0, 3.25), truncated=False)

    def fake_probe(actual_path):
        assert actual_path == path
        calls["probe"] = True
        return metadata

    def fake_frames(actual_path, *, duration_seconds, max_frames, max_width):
        assert actual_path == path
        calls["frames"] = (duration_seconds, max_frames, max_width)
        return [frame]

    def fake_scenes(actual_path, *, duration_seconds, threshold, max_scene_changes):
        assert actual_path == path
        calls["scenes"] = (duration_seconds, threshold, max_scene_changes)
        return scenes

    monkeypatch.setattr("mrhub.video_intelligence.analyzer.probe_video", fake_probe)
    monkeypatch.setattr("mrhub.video_intelligence.analyzer.extract_video_frames", fake_frames)
    monkeypatch.setattr("mrhub.video_intelligence.analyzer.detect_scene_boundaries", fake_scenes)

    result = analyzer.analyze(
        "owner-a",
        ASSET_ID,
        duration_seconds=30,
        max_frames=6,
        scene_threshold=0.4,
        max_scene_changes=10,
    )

    assert repository.lookups == [("owner-a", ASSET_ID)]
    assert result.asset_id == ASSET_ID
    assert result.content_hash == "a" * 64
    assert result.metadata is metadata
    assert result.analyzed_duration_seconds == 7.5
    assert result.frames == (frame,)
    assert result.scenes is scenes
    assert calls == {
        "probe": True,
        "frames": (7.5, 6, 1280),
        "scenes": (7.5, 0.4, 10),
    }


def test_analyzer_does_not_probe_an_asset_outside_owner_scope(tmp_path, monkeypatch):
    analyzer, repository, _ = make_analyzer(tmp_path, record=None)
    repository.get = lambda _owner, _asset: None
    monkeypatch.setattr(
        "mrhub.video_intelligence.analyzer.probe_video",
        lambda _path: pytest.fail("must not probe an asset not returned to this owner"),
    )

    with pytest.raises(VideoAssetAnalysisError, match="asset_not_found"):
        analyzer.analyze("different-owner", ASSET_ID)


def test_analyzer_rejects_non_video_asset_before_running_media_tools(tmp_path, monkeypatch):
    analyzer, _, _ = make_analyzer(tmp_path, {"media_type": "image/png"})
    monkeypatch.setattr(
        "mrhub.video_intelligence.analyzer.probe_video",
        lambda _path: pytest.fail("must not probe an image asset"),
    )

    with pytest.raises(VideoAssetAnalysisError, match="unsupported_media_type"):
        analyzer.analyze("owner-a", ASSET_ID)


def test_analyzer_fails_closed_when_technical_metadata_is_unavailable(tmp_path, monkeypatch):
    analyzer, _, _ = make_analyzer(tmp_path)
    monkeypatch.setattr(
        "mrhub.video_intelligence.analyzer.probe_video",
        lambda _path: VideoTechnicalMetadata(metadata_status="ffprobe_unavailable"),
    )
    monkeypatch.setattr(
        "mrhub.video_intelligence.analyzer.extract_video_frames",
        lambda *args, **kwargs: pytest.fail("frame extraction must not run"),
    )

    with pytest.raises(VideoAssetAnalysisError, match="video_metadata_unavailable"):
        analyzer.analyze("owner-a", ASSET_ID)


@pytest.mark.parametrize("duration", [float("nan"), float("inf"), 0.0, -1.0, 60.1])
def test_analyzer_rejects_invalid_duration_before_repository_lookup(tmp_path, duration):
    analyzer, repository, _ = make_analyzer(tmp_path)

    with pytest.raises(ValueError, match="duration_seconds"):
        analyzer.analyze("owner-a", ASSET_ID, duration_seconds=duration)

    assert repository.lookups == []


@pytest.mark.parametrize("max_frames", [True, 0, 13, 1.5])
def test_analyzer_rejects_invalid_frame_budget(tmp_path, max_frames):
    analyzer, repository, _ = make_analyzer(tmp_path)

    with pytest.raises(ValueError, match="max_frames"):
        analyzer.analyze("owner-a", ASSET_ID, max_frames=max_frames)

    assert repository.lookups == []


def test_analyzer_translates_frame_extraction_failures_to_sanitized_codes(
    tmp_path, monkeypatch
):
    analyzer, _, _ = make_analyzer(tmp_path)
    monkeypatch.setattr(
        "mrhub.video_intelligence.analyzer.probe_video",
        lambda _path: VideoTechnicalMetadata(
            duration_seconds=5,
            width=640,
            height=480,
            frame_rate=24,
            metadata_status="available",
        ),
    )
    monkeypatch.setattr(
        "mrhub.video_intelligence.analyzer.extract_video_frames",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            FrameExtractionError("extraction_timeout")
        ),
    )

    with pytest.raises(VideoAssetAnalysisError, match="frame_extraction_timeout"):
        analyzer.analyze("owner-a", ASSET_ID)


def test_analyzer_translates_scene_detection_failures_to_sanitized_codes(
    tmp_path, monkeypatch
):
    analyzer, _, _ = make_analyzer(tmp_path)
    monkeypatch.setattr(
        "mrhub.video_intelligence.analyzer.probe_video",
        lambda _path: VideoTechnicalMetadata(
            duration_seconds=5,
            width=640,
            height=480,
            frame_rate=24,
            metadata_status="available",
        ),
    )
    monkeypatch.setattr(
        "mrhub.video_intelligence.analyzer.extract_video_frames",
        lambda *args, **kwargs: [],
    )
    monkeypatch.setattr(
        "mrhub.video_intelligence.analyzer.detect_scene_boundaries",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            SceneDetectionError("detection_timeout")
        ),
    )

    with pytest.raises(VideoAssetAnalysisError, match="scene_detection_timeout"):
        analyzer.analyze("owner-a", ASSET_ID)
