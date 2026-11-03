import json
import subprocess

import pytest
from pydantic import ValidationError

from mrhub.api.routes.video_intelligence import PromptCompositionRequest, compose_prompt
from mrhub.config import get_settings
from mrhub.security.auth import AuthenticatedUser
from mrhub.video_intelligence.repository import VideoBrandRepository
from mrhub.video_intelligence.schemas import (
    AnalysisMode,
    BeatInstruction,
    BrandIdentity,
    VideoAnalysisRequest,
)
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


def test_authenticated_prompt_composition_returns_draft_without_execution():
    payload = PromptCompositionRequest(
        style_summary="Original cinematic 3D motion",
        beats=[{"start_seconds": 0, "end_seconds": 5, "generation_instruction": "Reveal an original object"}],
        duration_seconds=10,
        brand_name="MR_SIAVASH_IR_BOT",
    )
    result = compose_prompt(
        payload,
        AuthenticatedUser(user_id="owner-1", username="owner"),
    )
    assert result["status"] == "composed"
    assert result["execution"] == "not_started"
    assert "MR_SIAVASH_IR_BOT" in result["prompt"]



def test_video_prompt_rejects_invalid_or_oversized_timeline_inputs():
    with pytest.raises(ValidationError):
        BeatInstruction(
            start_seconds=5,
            end_seconds=4,
            generation_instruction="Invalid interval",
        )
    with pytest.raises(ValidationError):
        PromptCompositionRequest(
            style_summary="A bounded prompt",
            duration_seconds=5,
            beats=[{
                "start_seconds": 0,
                "end_seconds": 6,
                "generation_instruction": "Beat exceeds requested duration",
            }],
        )
    with pytest.raises(ValidationError):
        PromptCompositionRequest(
            style_summary="A bounded prompt",
            colors=["x" * 1000],
        )


def test_brand_profile_text_fields_have_per_item_limits():
    with pytest.raises(ValidationError):
        BrandIdentity(
            brand_name="Example",
            colors=["x" * 1000],
        )



def test_video_brand_profiles_are_owner_scoped():
    from client_helpers import authenticated_client

    client = authenticated_client()
    try:
        created = client.post(
            "/video-intelligence/brands",
            json={
                "brand_name": "Owner Brand",
                "colors": ["#071A12", "#00C878"],
                "font_preferences": ["Vazirmatn"],
            },
        )
        assert created.status_code == 201
        profile_id = created.json()["profile_id"]
        assert client.get(f"/video-intelligence/brands/{profile_id}").status_code == 200

        repository = VideoBrandRepository(get_settings().database_path)
        from uuid import UUID

        identifier = UUID(profile_id)
        assert repository.get("another-owner", identifier) is None
        assert repository.update(
            "another-owner",
            identifier,
            BrandIdentity(brand_name="Unauthorized rename"),
        ) is None
        assert repository.delete("another-owner", identifier) is False
        assert repository.get("local-owner", identifier)["brand_name"] == "Owner Brand"
    finally:
        client.close()



@pytest.mark.parametrize(
    "stdout",
    [
        b"[]",
        b'{"streams": "not-a-list", "format": {}}',
        b'{"streams": ["not-a-stream-object"], "format": {}}',
        b'{"streams": [], "format": []}',
    ],
)
def test_probe_video_rejects_malformed_ffprobe_json_shapes(
    tmp_path, monkeypatch, stdout
):
    source = tmp_path / "malformed.mp4"
    source.write_bytes(b"test")
    monkeypatch.setattr(
        "mrhub.video_intelligence.service.shutil.which",
        lambda _name: "/usr/bin/ffprobe",
    )
    monkeypatch.setattr(
        "mrhub.video_intelligence.service.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args=args, returncode=0, stdout=stdout, stderr=b""
        ),
    )

    result = probe_video(source)

    assert result.metadata_status == "probe_failed"



def test_probe_video_bounds_stream_count_and_discards_unneeded_stderr(tmp_path, monkeypatch):
    source = tmp_path / "sample.mp4"
    source.write_bytes(b"fixture")
    monkeypatch.setattr(
        "mrhub.video_intelligence.service.shutil.which",
        lambda _name: "/usr/bin/ffprobe",
    )
    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(
            args=command,
            returncode=0,
            stdout=json.dumps({
                "format": {"duration": "4.5"},
                "streams": [
                    {
                        "codec_type": "video",
                        "codec_name": "h264",
                        "width": 1280,
                        "height": 720,
                        "avg_frame_rate": "30/1",
                    },
                    {"codec_type": "audio", "codec_name": "aac"},
                ],
            }).encode(),
        )

    monkeypatch.setattr("mrhub.video_intelligence.service.subprocess.run", fake_run)

    result = probe_video(source)

    assert result.metadata_status == "available"
    assert result.duration_seconds == 4.5
    assert result.has_audio is True
    assert captured["command"][captured["command"].index("-max_streams") + 1] == "64"
    assert captured["kwargs"]["stdout"] == subprocess.PIPE
    assert captured["kwargs"]["stderr"] == subprocess.DEVNULL
    assert captured["kwargs"]["timeout"] == 12
    assert captured["kwargs"]["shell"] is False


def test_probe_video_fails_closed_when_ffprobe_times_out(tmp_path, monkeypatch):
    source = tmp_path / "sample.mp4"
    source.write_bytes(b"fixture")
    monkeypatch.setattr(
        "mrhub.video_intelligence.service.shutil.which",
        lambda _name: "/usr/bin/ffprobe",
    )

    def timeout(*_args, **_kwargs):
        raise subprocess.TimeoutExpired("ffprobe", 12)

    monkeypatch.setattr("mrhub.video_intelligence.service.subprocess.run", timeout)

    assert probe_video(source).metadata_status == "probe_failed"



@pytest.mark.parametrize(
    "stdout",
    [
        b'{"streams": [], "format": {"duration": "1.0"}}',
        b'{"streams": [{"codec_type": "video", "width": 1920, "height": 1080, "avg_frame_rate": "30/1"}], "format": {}}',
        b'{"streams": [{"codec_type": "video", "width": 1920, "height": 1080, "avg_frame_rate": "30/1"}], "format": {"duration": "NaN"}}',
        b'{"streams": [{"codec_type": "video", "width": 1920, "height": 1080, "avg_frame_rate": "30/0"}], "format": {"duration": "10"}}',
        b'{"streams": [{"codec_type": "video", "width": 0, "height": 1080, "avg_frame_rate": "30/1"}], "format": {"duration": "10"}}',
        b'{"streams": [{"codec_type": "video", "width": 1920, "height": 1080, "avg_frame_rate": "300/1"}], "format": {"duration": "10"}}',
    ],
)
def test_probe_video_rejects_missing_or_implausible_core_metadata(
    tmp_path, monkeypatch, stdout
):
    source = tmp_path / "invalid-metadata.mp4"
    source.write_bytes(b"test")
    monkeypatch.setattr(
        "mrhub.video_intelligence.service.shutil.which",
        lambda _name: "/usr/bin/ffprobe",
    )
    monkeypatch.setattr(
        "mrhub.video_intelligence.service.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args=args, returncode=0, stdout=stdout, stderr=b""
        ),
    )

    result = probe_video(source)

    assert result.metadata_status == "probe_failed"


def test_probe_video_accepts_valid_core_metadata(tmp_path, monkeypatch):
    source = tmp_path / "valid.mp4"
    source.write_bytes(b"test")
    stdout = (
        b'{"streams": [{"codec_type": "video", "codec_name": "h264", '
        b'"width": 1920, "height": 1080, "avg_frame_rate": "30000/1001"}, '
        b'{"codec_type": "audio"}], "format": {"duration": "12.5"}}'
    )
    monkeypatch.setattr(
        "mrhub.video_intelligence.service.shutil.which",
        lambda _name: "/usr/bin/ffprobe",
    )
    monkeypatch.setattr(
        "mrhub.video_intelligence.service.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args=args, returncode=0, stdout=stdout, stderr=b""
        ),
    )

    result = probe_video(source)

    assert result.metadata_status == "available"
    assert result.duration_seconds == 12.5
    assert result.width == 1920
    assert result.height == 1080
    assert result.frame_rate == 29.97
    assert result.has_audio is True
