import asyncio
import subprocess
import threading
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import HTTPException

from mrhub.api.routes import media as media_routes
from mrhub.security.auth import AuthenticatedUser


@pytest.mark.parametrize(
    "failure_point", ["output_target", "begin_processing", "already_processing"]
)
def test_transcode_releases_ffmpeg_slot_when_setup_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure_point: str,
) -> None:
    input_path = tmp_path / "input.mp4"
    input_path.write_bytes(b"fake mp4")
    asset_id = uuid4()
    semaphore = threading.BoundedSemaphore(1)

    class FakeRepository:
        def get(self, owner_user_id: str, requested_asset_id):
            assert owner_user_id == "local-owner"
            assert requested_asset_id == asset_id
            return {
                "source_asset_id": None,
                "media_type": "video/mp4",
                "storage_key": "input.mp4",
                "original_filename": "input.mp4",
            }

        def file_path(self, storage_key: str) -> Path:
            assert storage_key == "input.mp4"
            return input_path

        def new_output_target(self):
            if failure_point == "output_target":
                raise RuntimeError("output target setup failed")
            return str(uuid4()), "output.mp4", tmp_path / "output.mp4"

        def begin_processing(self, owner_user_id: str, requested_asset_id):
            if failure_point == "begin_processing":
                raise RuntimeError("database setup failed")
            if failure_point == "already_processing":
                return None
            return {"asset_id": str(requested_asset_id)}

    monkeypatch.setattr(media_routes, "_repository", FakeRepository)
    monkeypatch.setattr(media_routes.shutil, "which", lambda _name: "/usr/bin/ffmpeg")
    monkeypatch.setattr(media_routes, "_FFMPEG_SEMAPHORE", semaphore)

    user = AuthenticatedUser(user_id="local-owner", username="owner")
    if failure_point == "already_processing":
        with pytest.raises(HTTPException) as exc_info:
            media_routes.transcode_video(asset_id, user)
        assert exc_info.value.status_code == 409
    else:
        with pytest.raises(RuntimeError):
            media_routes.transcode_video(asset_id, user)

    # A subsequent request must still be able to reserve the single FFmpeg slot.
    assert semaphore.acquire(blocking=False)
    semaphore.release()



def test_upload_uses_one_buffer_and_releases_admission_slot(monkeypatch):
    semaphore = threading.BoundedSemaphore(1)
    monkeypatch.setattr(media_routes, "_UPLOAD_SEMAPHORE", semaphore)

    class FakeRequest:
        def __init__(self):
            self.headers = {
                "content-type": "image/png",
                "content-length": "8",
            }

        async def stream(self):
            yield b"\x89PNG\r\n\x1a\n"

    class FakeRepository:
        def store_upload(self, owner_user_id, filename, media_type, content):
            assert owner_user_id == "local-owner"
            assert filename == "sample.png"
            assert media_type == "image/png"
            assert isinstance(content, bytearray)
            assert content == b"\x89PNG\r\n\x1a\n"
            return {"asset_id": "asset-1", "storage_key": "private.png"}

    monkeypatch.setattr(media_routes, "_repository", FakeRepository)
    monkeypatch.setattr(media_routes, "_audit", lambda *_args: None)

    result = asyncio.run(
        media_routes.upload_asset(
            FakeRequest(),
            AuthenticatedUser(user_id="local-owner", username="owner"),
            "sample.png",
        )
    )

    assert result == {"asset_id": "asset-1"}
    assert semaphore.acquire(blocking=False)
    semaphore.release()


def test_upload_rejects_excess_concurrency_with_429(monkeypatch):
    semaphore = threading.BoundedSemaphore(1)
    assert semaphore.acquire(blocking=False)
    monkeypatch.setattr(media_routes, "_UPLOAD_SEMAPHORE", semaphore)

    class FakeRequest:
        def __init__(self):
            self.headers = {"content-type": "image/png"}

        async def stream(self):
            pytest.fail("A rejected upload must not consume the request body")
            yield b""

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            media_routes.upload_asset(
                FakeRequest(),
                AuthenticatedUser(user_id="local-owner", username="owner"),
                "sample.png",
            )
        )

    assert exc_info.value.status_code == 429
    semaphore.release()



def test_upload_keeps_admission_slot_until_storage_thread_finishes_on_cancel(monkeypatch):
    semaphore = threading.BoundedSemaphore(1)
    started = threading.Event()
    finish_storage = threading.Event()
    monkeypatch.setattr(media_routes, "_UPLOAD_SEMAPHORE", semaphore)

    class FakeRequest:
        def __init__(self):
            self.headers = {"content-type": "image/png", "content-length": "8"}

        async def stream(self):
            yield b"\x89PNG\r\n\x1a\n"

    class BlockingRepository:
        def store_upload(self, *_args):
            started.set()
            assert finish_storage.wait(timeout=5)
            return {"asset_id": "asset-1", "storage_key": "private.png"}

    monkeypatch.setattr(media_routes, "_repository", BlockingRepository)
    monkeypatch.setattr(media_routes, "_audit", lambda *_args: None)

    async def exercise_cancellation():
        task = asyncio.create_task(
            media_routes.upload_asset(
                FakeRequest(),
                AuthenticatedUser(user_id="local-owner", username="owner"),
                "sample.png",
            )
        )
        assert await asyncio.to_thread(started.wait, 2)
        task.cancel()
        await asyncio.sleep(0)
        assert not semaphore.acquire(blocking=False)
        finish_storage.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert semaphore.acquire(blocking=False)
        semaphore.release()

    asyncio.run(exercise_cancellation())



def test_transcode_bounds_decoder_resources_and_discards_process_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    input_path = tmp_path / "input.mp4"
    input_path.write_bytes(b"fake mp4")
    output_path = tmp_path / "output.mp4"
    asset_id = uuid4()
    observed = {}

    class FakeRepository:
        storage_root = tmp_path

        def get(self, owner_user_id: str, requested_asset_id):
            assert owner_user_id == "local-owner"
            assert requested_asset_id == asset_id
            return {
                "source_asset_id": None,
                "media_type": "video/mp4",
                "storage_key": "input.mp4",
                "original_filename": "input.mp4",
            }

        def file_path(self, storage_key: str) -> Path:
            assert storage_key == "input.mp4"
            return input_path

        def new_output_target(self):
            return "output-id", "output.mp4", output_path

        def begin_processing(self, owner_user_id: str, requested_asset_id):
            return {"asset_id": str(requested_asset_id)}

        def register_transcoded_output(self, *_args):
            return {
                "asset_id": "output-id",
                "storage_key": "output.mp4",
                "media_type": "video/mp4",
                "original_filename": "output.mp4",
            }

        def fail_processing(self, *_args):
            pytest.fail("A successful fake transcode must not mark processing failed")

    def fake_run(command, **kwargs):
        observed["command"] = command
        observed["kwargs"] = kwargs
        Path(command[-1]).write_bytes(b"transcoded-video")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(media_routes, "_repository", FakeRepository)
    monkeypatch.setattr(media_routes.shutil, "which", lambda _name: "/usr/bin/ffmpeg")
    monkeypatch.setattr(media_routes.subprocess, "run", fake_run)
    monkeypatch.setattr(media_routes, "_audit", lambda *_args: None)
    monkeypatch.setattr(
        media_routes, "_FFMPEG_SEMAPHORE", threading.BoundedSemaphore(1)
    )

    result = media_routes.transcode_video(
        asset_id,
        AuthenticatedUser(user_id="local-owner", username="owner"),
    )

    command = observed["command"]
    kwargs = observed["kwargs"]
    assert result["status"] == "succeeded"
    assert command[command.index("-max_pixels") + 1] == "33554432"
    assert command.index("-max_pixels") < command.index("-i")
    assert kwargs["stdout"] == subprocess.DEVNULL
    assert kwargs["stderr"] == subprocess.DEVNULL
    assert "capture_output" not in kwargs
    assert kwargs["shell"] is False
    assert kwargs["timeout"] == 120
