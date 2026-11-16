import pytest
from pydantic import ValidationError

from mrhub.video_intelligence.edit_spec import build_edit_specification
from mrhub.video_intelligence.schemas import AnalysisMode, VideoAnalysisRequest
from mrhub.video_intelligence.timeline import VideoTimeline, build_video_timeline


def _asset(asset_id, duration, scenes):
    return {
        "asset_id": asset_id,
        "technical_metadata": {
            "metadata_status": "available",
            "width": 1920,
            "height": 1080,
            "frame_rate": 30.0,
            "codec": "h264",
            "has_audio": True,
        },
        "analysis_window_seconds": duration,
        "scene_start_timestamps": scenes,
        "scene_boundaries_truncated": False,
        "semantic_visual_analysis": {"status": "not_configured"},
    }


def _specification(asset_results, duration=10):
    request = VideoAnalysisRequest(
        mode=AnalysisMode.FAITHFUL,
        source_asset_ids=[item["asset_id"] for item in asset_results],
        duration_seconds=duration,
        output_aspect_ratio="16:9",
        include_audio_analysis=False,
    )
    return build_edit_specification(request, asset_results)


def test_timeline_splits_source_at_scene_boundaries_and_trims_to_target():
    specification = _specification(
        [_asset("source-a", 20.0, [0.0, 2.0, 5.0, 8.0])],
        duration=7,
    )

    timeline = build_video_timeline(specification)

    assert timeline.actual_duration_seconds == 7.0
    assert timeline.duration_shortfall_seconds == 0.0
    assert [
        (clip.source_start_seconds, clip.source_end_seconds)
        for clip in timeline.video_track
    ] == [(0.0, 2.0), (2.0, 5.0), (5.0, 7.0)]
    assert [clip.transition_in for clip in timeline.video_track] == [
        "none", "cut", "cut"
    ]
    assert timeline.audio_analysis_status == "not_requested"
    assert timeline.audio_render_status == "source_audio_passthrough"
    assert all(clip.include_source_audio is True for clip in timeline.video_track)
    assert timeline.render_status == "not_implemented"


def test_timeline_allocates_time_across_sources_and_redistributes_short_source():
    specification = _specification(
        [
            _asset("short-source", 2.0, [0.0]),
            _asset("long-source", 20.0, [0.0, 3.0, 7.0]),
        ],
        duration=10,
    )

    timeline = build_video_timeline(specification)

    first = [clip for clip in timeline.video_track if clip.source_asset_id == "short-source"]
    second = [clip for clip in timeline.video_track if clip.source_asset_id == "long-source"]
    assert sum(c.timeline_end_seconds - c.timeline_start_seconds for c in first) == 2.0
    assert sum(c.timeline_end_seconds - c.timeline_start_seconds for c in second) == 8.0
    assert timeline.actual_duration_seconds == 10.0


def test_timeline_reports_shortfall_when_all_sources_are_short():
    specification = _specification(
        [_asset("source-a", 2.0, [0.0]), _asset("source-b", 3.0, [0.0])],
        duration=10,
    )

    timeline = build_video_timeline(specification)

    assert timeline.actual_duration_seconds == 5.0
    assert timeline.duration_shortfall_seconds == 5.0


def test_timeline_contract_rejects_gaps_and_overlaps():
    with pytest.raises(ValidationError):
        VideoTimeline(
            output_aspect_ratio="16:9",
            requested_duration_seconds=6,
            actual_duration_seconds=6,
            duration_shortfall_seconds=0,
            audio_analysis_status="not_requested",
            audio_render_status="not_implemented",
            timeline_status="validated_cut_only",
            render_status="not_implemented",
            video_track=[
                {
                    "clip_id": "clip-001",
                    "source_asset_id": "source-a",
                    "source_scene_index": 0,
                    "source_start_seconds": 0,
                    "source_end_seconds": 3,
                    "timeline_start_seconds": 0,
                    "timeline_end_seconds": 3,
                    "transition_in": "none",
                },
                {
                    "clip_id": "clip-002",
                    "source_asset_id": "source-a",
                    "source_scene_index": 1,
                    "source_start_seconds": 3,
                    "source_end_seconds": 6,
                    "timeline_start_seconds": 4,
                    "timeline_end_seconds": 7,
                    "transition_in": "cut",
                },
            ],
        )


def test_timeline_rejects_source_and_timeline_duration_mismatch():
    with pytest.raises(ValidationError):
        VideoTimeline(
            output_aspect_ratio="16:9",
            requested_duration_seconds=3,
            actual_duration_seconds=3,
            duration_shortfall_seconds=0,
            audio_analysis_status="not_requested",
            audio_render_status="not_implemented",
            timeline_status="validated_cut_only",
            render_status="not_implemented",
            video_track=[
                {
                    "clip_id": "clip-001",
                    "source_asset_id": "source-a",
                    "source_scene_index": 0,
                    "source_start_seconds": 0,
                    "source_end_seconds": 2,
                    "timeline_start_seconds": 0,
                    "timeline_end_seconds": 3,
                    "transition_in": "none",
                }
            ],
        )



def test_timeline_preserves_only_audio_confirmed_by_source_analysis():
    with_audio = _asset("audio-source", 3.0, [0.0])
    without_audio = _asset("silent-source", 3.0, [0.0])
    without_audio["technical_metadata"]["has_audio"] = False
    unknown_audio = _asset("unknown-source", 3.0, [0.0])
    unknown_audio["technical_metadata"].pop("has_audio")

    timeline = build_video_timeline(
        _specification([with_audio, without_audio, unknown_audio], duration=9)
    )

    clips = {clip.source_asset_id: clip for clip in timeline.video_track}
    assert clips["audio-source"].include_source_audio is True
    assert clips["silent-source"].include_source_audio is None
    assert clips["unknown-source"].include_source_audio is None
    assert timeline.audio_render_status == "source_audio_passthrough"


def test_timeline_audio_status_must_match_explicit_audio_clips():
    timeline = build_video_timeline(
        _specification([_asset("audio-source", 4.0, [0.0])], duration=4)
    )
    payload = timeline.model_dump(mode="json")
    payload["audio_render_status"] = "not_implemented"

    with pytest.raises(ValidationError, match="Audio render status"):
        VideoTimeline.model_validate(payload)


def test_timeline_rejects_source_audio_gain_above_the_bounded_range():
    timeline = build_video_timeline(
        _specification([_asset("audio-source", 4.0, [0.0])], duration=4)
    )
    payload = timeline.model_dump(mode="json")
    payload["video_track"][0]["source_audio_volume"] = 2.1

    with pytest.raises(ValidationError):
        VideoTimeline.model_validate(payload)
