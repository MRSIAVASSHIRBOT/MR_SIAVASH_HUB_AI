import subprocess

from mrhub.video_intelligence.service import probe_video


def test_probe_video_rejects_output_above_tightened_limit(tmp_path, monkeypatch):
    source = tmp_path / "oversized.mp4"
    source.write_bytes(b"fixture")
    monkeypatch.setattr(
        "mrhub.video_intelligence.service.shutil.which",
        lambda _name: "/usr/bin/ffprobe",
    )
    monkeypatch.setattr(
        "mrhub.video_intelligence.service.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args=args,
            returncode=0,
            stdout=b"x" * (64 * 1024 + 1),
            stderr=b"",
        ),
    )

    result = probe_video(source)

    assert result.metadata_status == "probe_failed"


def test_probe_video_requests_only_bounded_metadata_fields(tmp_path, monkeypatch):
    source = tmp_path / "sample.mp4"
    source.write_bytes(b"fixture")
    monkeypatch.setattr(
        "mrhub.video_intelligence.service.shutil.which",
        lambda _name: "/usr/bin/ffprobe",
    )
    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        return subprocess.CompletedProcess(
            args=command,
            returncode=0,
            stdout=(
                b'{"format":{"duration":"1.0"},"streams":['
                b'{"codec_type":"video","codec_name":"h264","width":640,'
                b'"height":360,"avg_frame_rate":"30/1"}]}'
            ),
            stderr=b"",
        )

    monkeypatch.setattr("mrhub.video_intelligence.service.subprocess.run", fake_run)

    result = probe_video(source)

    assert result.metadata_status == "available"
    assert "-show_entries" in captured["command"]
    entries = captured["command"][captured["command"].index("-show_entries") + 1]
    assert entries == "format=duration:stream=codec_type,codec_name,width,height,avg_frame_rate"
    assert captured["command"][captured["command"].index("-max_streams") + 1] == "64"
