import subprocess
from pathlib import Path

import pytest

from mrhub.video_intelligence import frames


def _source(tmp_path: Path) -> Path:
    source = tmp_path / "owned-video.mp4"
    source.write_bytes(b"video-data")
    return source


def test_extract_video_frames_returns_bounded_uniform_samples(monkeypatch, tmp_path):
    source = _source(tmp_path)
    monkeypatch.setattr(frames.shutil, "which", lambda _name: "/usr/bin/ffmpeg")
    observed = {}

    def fake_run(command, **kwargs):
        observed["command"] = command
        observed["kwargs"] = kwargs
        output_pattern = Path(command[-1])
        for index in range(1, 4):
            output_pattern.with_name(f"frame-{index:02d}.jpg").write_bytes(
                f"jpeg-{index}".encode()
            )
        return subprocess.CompletedProcess(command, 0, b"", b"")

    monkeypatch.setattr(frames.subprocess, "run", fake_run)

    result = frames.extract_video_frames(
        source, duration_seconds=6, max_frames=3, max_width=640
    )

    assert [frame.timestamp_seconds for frame in result] == [0.0, 2.0, 4.0]
    assert [frame.jpeg_bytes for frame in result] == [b"jpeg-1", b"jpeg-2", b"jpeg-3"]
    assert observed["kwargs"]["shell"] is False
    assert observed["kwargs"]["stdout"] == subprocess.DEVNULL
    assert observed["kwargs"]["stderr"] == subprocess.DEVNULL
    assert observed["kwargs"]["timeout"] == 30
    filter_value = observed["command"][observed["command"].index("-vf") + 1]
    assert "min(640,ih)" in filter_value
    assert "force_original_aspect_ratio=decrease" in filter_value
    assert observed["command"][observed["command"].index("-frames:v") + 1] == "3"
    assert "-protocol_whitelist" in observed["command"]


def test_extract_video_frames_rejects_invalid_limits_before_execution(monkeypatch, tmp_path):
    source = _source(tmp_path)
    monkeypatch.setattr(frames.shutil, "which", lambda _name: "/usr/bin/ffmpeg")
    monkeypatch.setattr(
        frames.subprocess, "run",
        lambda *_args, **_kwargs: pytest.fail("subprocess must not run"),
    )

    with pytest.raises(ValueError):
        frames.extract_video_frames(source, duration_seconds=61)
    with pytest.raises(ValueError):
        frames.extract_video_frames(source, duration_seconds=5, max_frames=13)
    with pytest.raises(ValueError):
        frames.extract_video_frames(source, duration_seconds=5, max_width=4096)


def test_extract_video_frames_reports_missing_source(tmp_path):
    with pytest.raises(frames.FrameExtractionError) as error:
        frames.extract_video_frames(
            tmp_path / "missing.mp4", duration_seconds=5
        )
    assert error.value.reason_code == "source_missing"


def test_extract_video_frames_reports_missing_ffmpeg(monkeypatch, tmp_path):
    source = _source(tmp_path)
    monkeypatch.setattr(frames.shutil, "which", lambda _name: None)

    with pytest.raises(frames.FrameExtractionError) as error:
        frames.extract_video_frames(source, duration_seconds=5)
    assert error.value.reason_code == "ffmpeg_unavailable"


def test_extract_video_frames_enforces_per_frame_size(monkeypatch, tmp_path):
    source = _source(tmp_path)
    monkeypatch.setattr(frames.shutil, "which", lambda _name: "/usr/bin/ffmpeg")

    def fake_run(command, **_kwargs):
        Path(command[-1]).with_name("frame-01.jpg").write_bytes(
            b"x" * (frames._MAX_FRAME_BYTES + 1)
        )
        return subprocess.CompletedProcess(command, 0, b"", b"")

    monkeypatch.setattr(frames.subprocess, "run", fake_run)

    with pytest.raises(frames.FrameExtractionError) as error:
        frames.extract_video_frames(source, duration_seconds=5)
    assert error.value.reason_code == "frame_size_out_of_range"


def test_extract_video_frames_maps_timeout_to_stable_error(monkeypatch, tmp_path):
    source = _source(tmp_path)
    monkeypatch.setattr(frames.shutil, "which", lambda _name: "/usr/bin/ffmpeg")

    def fake_run(command, **_kwargs):
        raise subprocess.TimeoutExpired(command, timeout=30)

    monkeypatch.setattr(frames.subprocess, "run", fake_run)

    with pytest.raises(frames.FrameExtractionError) as error:
        frames.extract_video_frames(source, duration_seconds=5)
    assert error.value.reason_code == "extraction_timeout"
