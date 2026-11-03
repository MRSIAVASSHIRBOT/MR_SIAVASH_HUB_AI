import asyncio
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
        headers = {
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
        headers = {"content-type": "image/png"}

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
