import pathlib
import subprocess

import pytest

from mrhub.video_intelligence import scenes


def _source(tmp_path: pathlib.Path) -> pathlib.Path:
    path = tmp_path / "owned-video.mp4"
    path.write_bytes(b"video")
    return path


def _framehash(*pts: int, time_base: str = "1/24") -> bytes:
    header = (
        "#format: frame checksums\n"
        "#version: 2\n"
        "#hash: SHA256\n"
        f"#tb 0: {time_base}\n"
        "#media_type 0: video\n"
        "#codec_id 0: rawvideo\n"
        "#dimensions 0: 640x360\n"
        "#sar 0: 1/1\n"
        "#stream#, dts, pts, duration, size, hash\n"
    )
    rows = "".join(f"0, {value}, {value}, 1, 100, {'a' * 64}\n" for value in pts)
    return (header + rows).encode("ascii")


def test_detect_scene_boundaries_parses_pts_and_declared_time_base(monkeypatch, tmp_path):
    source = _source(tmp_path)
    observed = {}

    def fake_run(command, **kwargs):
        observed["command"] = command
        observed["kwargs"] = kwargs
        return subprocess.CompletedProcess(command, 0, _framehash(48, 72), b"")

    monkeypatch.setattr(scenes.shutil, "which", lambda _name: "/usr/bin/ffmpeg")
    monkeypatch.setattr(scenes.subprocess, "run", fake_run)

    result = scenes.detect_scene_boundaries(source, duration_seconds=4)

    assert result.scene_start_times == (0.0, 2.0, 3.0)
    assert result.scene_count == 3
    assert result.truncated is False
    command = observed["command"]
    assert command[command.index("-vf") + 1].startswith("select='gt(scene,0.300)'")
    assert command[command.index("-frames:v") + 1] == "25"
    assert command[-2:] == ["framehash", "-"]
    assert observed["kwargs"]["shell"] is False
    assert observed["kwargs"]["stdin"] == subprocess.DEVNULL
    assert observed["kwargs"]["stdout"] == subprocess.PIPE
    assert observed["kwargs"]["stderr"] == subprocess.DEVNULL
    assert observed["kwargs"]["timeout"] == 30


def test_detect_scene_boundaries_marks_capped_results_as_truncated(monkeypatch, tmp_path):
    source = _source(tmp_path)
    captured = {}
    monkeypatch.setattr(scenes.shutil, "which", lambda _name: "/usr/bin/ffmpeg")

    def fake_run(command, **_kwargs):
        captured["limit"] = command[command.index("-frames:v") + 1]
        return subprocess.CompletedProcess(command, 0, _framehash(24, 48, 72), b"")

    monkeypatch.setattr(scenes.subprocess, "run", fake_run)

    result = scenes.detect_scene_boundaries(source, duration_seconds=4, max_scene_changes=2)

    assert captured["limit"] == "3"
    assert result.scene_start_times == (0.0, 1.0, 2.0)
    assert result.truncated is True


def test_detect_scene_boundaries_returns_opening_scene_when_no_cuts(monkeypatch, tmp_path):
    source = _source(tmp_path)
    monkeypatch.setattr(scenes.shutil, "which", lambda _name: "/usr/bin/ffmpeg")
    monkeypatch.setattr(
        scenes.subprocess,
        "run",
        lambda command, **_kwargs: subprocess.CompletedProcess(command, 0, _framehash(), b""),
    )

    result = scenes.detect_scene_boundaries(source, duration_seconds=4)

    assert result.scene_start_times == (0.0,)
    assert result.scene_count == 1
    assert result.truncated is False


@pytest.mark.parametrize(
    "output",
    [
        b"not a framehash document",
        b"#tb 0: 1/0\n0, 0, 24, 1, 100, deadbeef\n",
        b"#tb 0: 1/24\n0, 0, N/A, 1, 100, deadbeef\n",
        b"#tb 0: 1/24\n0, 0, 24, 1, 100\n",
        b"\xff",
        _framehash(10**400),
    ],
)
def test_parse_framehash_rejects_malformed_output(output):
    with pytest.raises(scenes.SceneDetectionError):
        scenes._parse_framehash_timestamps(output)


def test_detect_scene_boundaries_rejects_invalid_limits_before_execution(monkeypatch, tmp_path):
    source = _source(tmp_path)
    monkeypatch.setattr(scenes.shutil, "which", lambda _name: "/usr/bin/ffmpeg")
    monkeypatch.setattr(
        scenes.subprocess,
        "run",
        lambda *_args, **_kwargs: pytest.fail("FFmpeg must not run"),
    )

    with pytest.raises(ValueError):
        scenes.detect_scene_boundaries(source, duration_seconds=61)
    with pytest.raises(ValueError):
        scenes.detect_scene_boundaries(source, duration_seconds=5, threshold=1.1)
    with pytest.raises(ValueError):
        scenes.detect_scene_boundaries(source, duration_seconds=5, max_scene_changes=25)


def test_detect_scene_boundaries_maps_execution_failures(monkeypatch, tmp_path):
    source = _source(tmp_path)
    monkeypatch.setattr(scenes.shutil, "which", lambda _name: "/usr/bin/ffmpeg")

    def timeout(command, **_kwargs):
        raise subprocess.TimeoutExpired(command, timeout=30)

    monkeypatch.setattr(scenes.subprocess, "run", timeout)
    with pytest.raises(scenes.SceneDetectionError) as error:
        scenes.detect_scene_boundaries(source, duration_seconds=5)
    assert error.value.reason_code == "detection_timeout"

    monkeypatch.setattr(
        scenes.subprocess,
        "run",
        lambda command, **_kwargs: subprocess.CompletedProcess(command, 1, b"", b""),
    )
    with pytest.raises(scenes.SceneDetectionError) as error:
        scenes.detect_scene_boundaries(source, duration_seconds=5)
    assert error.value.reason_code == "detection_failed"


def test_detect_scene_boundaries_rejects_timestamp_beyond_clip_duration(monkeypatch, tmp_path):
    source = _source(tmp_path)
    monkeypatch.setattr(scenes.shutil, "which", lambda _name: "/usr/bin/ffmpeg")
    monkeypatch.setattr(
        scenes.subprocess,
        "run",
        lambda command, **_kwargs: subprocess.CompletedProcess(command, 0, _framehash(240), b""),
    )

    with pytest.raises(scenes.SceneDetectionError) as error:
        scenes.detect_scene_boundaries(source, duration_seconds=4)
    assert error.value.reason_code == "scene_timestamp_out_of_range"


def test_detect_scene_boundaries_rejects_cut_even_within_old_tolerance(monkeypatch, tmp_path):
    source = _source(tmp_path)
    monkeypatch.setattr(scenes.shutil, "which", lambda _name: "/usr/bin/ffmpeg")
    monkeypatch.setattr(
        scenes.subprocess,
        "run",
        lambda command, **_kwargs: subprocess.CompletedProcess(command, 0, _framehash(99), b""),
    )

    with pytest.raises(scenes.SceneDetectionError) as error:
        scenes.detect_scene_boundaries(source, duration_seconds=4)
    assert error.value.reason_code == "scene_timestamp_out_of_range"


def test_detect_scene_boundaries_rejects_oversized_framehash_output(monkeypatch, tmp_path):
    source = _source(tmp_path)
    monkeypatch.setattr(scenes.shutil, "which", lambda _name: "/usr/bin/ffmpeg")
    monkeypatch.setattr(
        scenes.subprocess,
        "run",
        lambda command, **_kwargs: subprocess.CompletedProcess(
            command, 0, b"x" * (scenes._MAX_FRAMEHASH_OUTPUT_BYTES + 1), b""
        ),
    )

    with pytest.raises(scenes.SceneDetectionError) as error:
        scenes.detect_scene_boundaries(source, duration_seconds=5)
    assert error.value.reason_code == "scene_output_too_large"


def test_detect_scene_boundaries_rejects_missing_or_oversized_source(monkeypatch, tmp_path):
    missing = tmp_path / "missing.mp4"
    with pytest.raises(scenes.SceneDetectionError) as error:
        scenes.detect_scene_boundaries(missing, duration_seconds=5)
    assert error.value.reason_code == "source_missing"

    source = _source(tmp_path)
    monkeypatch.setattr(scenes, "_MAX_SOURCE_BYTES", 4)
    monkeypatch.setattr(
        scenes.subprocess,
        "run",
        lambda *_args, **_kwargs: pytest.fail("FFmpeg must not run"),
    )
    with pytest.raises(scenes.SceneDetectionError) as error:
        scenes.detect_scene_boundaries(source, duration_seconds=5)
    assert error.value.reason_code == "source_size_out_of_range"


def test_detect_scene_boundaries_rejects_missing_ffmpeg(monkeypatch, tmp_path):
    source = _source(tmp_path)
    monkeypatch.setattr(scenes.shutil, "which", lambda _name: None)

    with pytest.raises(scenes.SceneDetectionError) as error:
        scenes.detect_scene_boundaries(source, duration_seconds=5)
    assert error.value.reason_code == "ffmpeg_unavailable"


def test_detect_scene_boundaries_rejects_non_monotonic_timestamps(monkeypatch, tmp_path):
    source = _source(tmp_path)
    monkeypatch.setattr(scenes.shutil, "which", lambda _name: "/usr/bin/ffmpeg")
    monkeypatch.setattr(
        scenes.subprocess,
        "run",
        lambda command, **_kwargs: subprocess.CompletedProcess(command, 0, _framehash(72, 48), b""),
    )

    with pytest.raises(scenes.SceneDetectionError) as error:
        scenes.detect_scene_boundaries(source, duration_seconds=4)
    assert error.value.reason_code == "scene_timestamps_not_monotonic"
