from pydantic import ValidationError

from mrhub.video_intelligence.schemas import AnalysisMode, VideoAnalysisRequest
from mrhub.video_intelligence.service import build_generation_prompt, probe_video


def test_video_analysis_request_bounds_sources_and_duration():
    request = VideoAnalysisRequest(
        mode=AnalysisMode.FAITHFUL,
        source_asset_ids=["asset-1"],
        duration_seconds=10,
    )
    assert request.output_aspect_ratio == "9:16"
    try:
        VideoAnalysisRequest(
            mode=AnalysisMode.FUSION,
            source_asset_ids=[f"asset-{index}" for index in range(6)],
        )
    except ValidationError:
        pass
    else:
        raise AssertionError("More than five source assets must be rejected")
    try:
        VideoAnalysisRequest(
            mode=AnalysisMode.FUSION,
            source_asset_ids=["asset-1"],
            duration_seconds=120,
        )
    except ValidationError:
        pass
    else:
        raise AssertionError("Duration above 60 seconds must be rejected")


def test_prompt_builder_preserves_timeline_and_brand_constraints():
    prompt = build_generation_prompt(
        style_summary="Glossy 3D product motion with restrained camera movement",
        beats=[{
            "start_seconds": 0,
            "end_seconds": 4,
            "generation_instruction": "Reveal an original geometric product silhouette",
            "transition_to_next": "soft light wipe",
        }],
        duration_seconds=10,
        aspect_ratio="9:16",
        brand_name="MR_SIAVASH_IR_BOT",
        colors=["#071A12", "#00C878"],
        typography="Modern Persian-compatible sans serif",
    )
    assert "0s–4s" in prompt
    assert "#00C878" in prompt
    assert "MR_SIAVASH_IR_BOT" in prompt
    assert "Do not reproduce protected logos" in prompt


def test_probe_video_returns_unavailable_or_failed_for_missing_file(tmp_path, monkeypatch):
    monkeypatch.setattr("mrhub.video_intelligence.service.shutil.which", lambda _name: None)
    result = probe_video(tmp_path / "missing.mp4")
    assert result.metadata_status == "ffprobe_unavailable"


def test_probe_video_does_not_accept_nonexistent_path(tmp_path, monkeypatch):
    monkeypatch.setattr("mrhub.video_intelligence.service.shutil.which", lambda _name: "/usr/bin/ffprobe")
    result = probe_video(tmp_path / "missing.mp4")
    assert result.metadata_status == "probe_failed"
