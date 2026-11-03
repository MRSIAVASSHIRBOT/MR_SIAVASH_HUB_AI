import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from mrhub.video_intelligence import render
from mrhub.video_intelligence.render import (
    VideoRenderError,
    build_ffmpeg_command,
    render_video_timeline,
)
from mrhub.video_intelligence.timeline import VideoTimeline


def _timeline():
    return VideoTimeline(
        output_aspect_ratio="16:9",
        requested_duration_seconds=4,
        actual_duration_seconds=4.0,
        duration_shortfall_seconds=0.0,
        audio_analysis_status="not_requested",
        audio_render_status="not_implemented",
        timeline_status="validated_cut_only",
        render_status="not_implemented",
        video_track=[
            {
                "clip_id": "clip-001",
                "source_asset_id": "asset-a",
                "source_scene_index": 0,
                "source_start_seconds": 0.0,
                "source_end_seconds": 2.0,
                "timeline_start_seconds": 0.0,
                "timeline_end_seconds": 2.0,
                "transition_in": "none",
            },
            {
                "clip_id": "clip-002",
                "source_asset_id": "asset-a",
                "source_scene_index": 1,
                "source_start_seconds": 2.0,
                "source_end_seconds": 4.0,
                "timeline_start_seconds": 2.0,
                "timeline_end_seconds": 4.0,
                "transition_in": "cut",
            },
        ],
    )


def test_command_uses_numeric_cut_data_and_silent_output(tmp_path):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source")
    output = tmp_path / "render.partial.mp4"

    command = build_ffmpeg_command(
        ffmpeg_binary="/usr/bin/ffmpeg",
        timeline=_timeline(),
        source_paths={"asset-a": source},
        temporary_output=output,
    )

    assert command.count("-i") == 2
    assert "-an" in command
    assert "-map" in command
    assert "concat=n=2:v=1:a=0[outv]" in command[command.index("-filter_complex") + 1]
    assert "trim=start=0.000:end=2.000" in command[command.index("-filter_complex") + 1]
    assert "shell" not in command
    assert command[-1] == str(output)


def test_renderer_publishes_only_after_verified_ffprobe(tmp_path, monkeypatch):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source")
    output = tmp_path / "final.mp4"
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        if command[0] == "/usr/bin/ffmpeg":
            Path(command[-1]).write_bytes(b"valid-mp4-placeholder")
            return SimpleNamespace(returncode=0, stdout=b"")
        return SimpleNamespace(
            returncode=0,
            stdout=(
                b'{"format":{"format_name":"mov,mp4,m4a","duration":"4.0"},'
                b'"streams":[{"codec_type":"video","width":1920,"height":1080}]}'
            ),
        )

    monkeypatch.setattr(render.subprocess, "run", fake_run)
    result = render_video_timeline(
        timeline=_timeline(),
        source_paths={"asset-a": source},
        output_path=output,
        ffmpeg_binary="/usr/bin/ffmpeg",
        ffprobe_binary="/usr/bin/ffprobe",
    )

    assert output.is_file()
    assert result.duration_seconds == 4.0
    assert (result.width, result.height) == (1920, 1080)
    assert len(calls) == 2
    assert calls[0][1]["shell"] is False
    assert calls[0][1]["timeout"] == render.MAX_RENDER_TIMEOUT_SECONDS
    assert not list(tmp_path.glob("*.partial.mp4"))


def test_renderer_removes_temporary_output_when_ffmpeg_fails(tmp_path, monkeypatch):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source")
    output = tmp_path / "final.mp4"

    def fake_run(command, **kwargs):
        Path(command[-1]).write_bytes(b"partial")
        return SimpleNamespace(returncode=1, stdout=b"")

    monkeypatch.setattr(render.subprocess, "run", fake_run)
    with pytest.raises(VideoRenderError, match="ffmpeg_failed"):
        render_video_timeline(
            timeline=_timeline(),
            source_paths={"asset-a": source},
            output_path=output,
            ffmpeg_binary="/usr/bin/ffmpeg",
            ffprobe_binary="/usr/bin/ffprobe",
        )

    assert not output.exists()
    assert not list(tmp_path.glob(".*.partial.mp4"))


def test_renderer_rejects_missing_owner_resolved_source_before_process(tmp_path, monkeypatch):
    output = tmp_path / "final.mp4"
    called = False

    def fake_run(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("FFmpeg must not run without every source")

    monkeypatch.setattr(render.subprocess, "run", fake_run)
    with pytest.raises(VideoRenderError, match="render_source_missing"):
        render_video_timeline(
            timeline=_timeline(),
            source_paths={},
            output_path=output,
            ffmpeg_binary="/usr/bin/ffmpeg",
            ffprobe_binary="/usr/bin/ffprobe",
        )
    assert called is False



def test_real_ffmpeg_render_produces_probeable_mp4_when_available(tmp_path):
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    if ffmpeg is None or ffprobe is None:
        pytest.skip("FFmpeg and FFprobe are required for the real-render smoke test")

    source = tmp_path / "generated-source.mp4"
    output = tmp_path / "generated-output.mp4"
    generated = subprocess.run(
        [
            ffmpeg,
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=blue:s=320x240:d=4",
            "-an",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-t",
            "4",
            str(source),
        ],
        shell=False,
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=30,
    )
    if generated.returncode != 0:
        pytest.skip("The installed FFmpeg build cannot generate the synthetic test source")

    result = render_video_timeline(
        timeline=_timeline(),
        source_paths={"asset-a": source},
        output_path=output,
        ffmpeg_binary=ffmpeg,
        ffprobe_binary=ffprobe,
    )

    assert output.is_file()
    assert output.stat().st_size > 0
    assert result.duration_seconds == pytest.approx(4.0, abs=0.5)
    assert (result.width, result.height) == (1920, 1080)
