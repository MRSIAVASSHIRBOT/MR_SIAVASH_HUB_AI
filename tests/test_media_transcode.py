import threading
from pathlib import Path
from uuid import uuid4

import pytest

from mrhub.api.routes import media as media_routes
from mrhub.security.auth import AuthenticatedUser


@pytest.mark.parametrize("failure_point", ["output_target", "begin_processing"])
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
            return {"asset_id": str(requested_asset_id)}

    monkeypatch.setattr(media_routes, "_repository", FakeRepository)
    monkeypatch.setattr(media_routes.shutil, "which", lambda _name: "/usr/bin/ffmpeg")
    monkeypatch.setattr(media_routes, "_FFMPEG_SEMAPHORE", semaphore)

    user = AuthenticatedUser(user_id="local-owner", username="owner")
    with pytest.raises(RuntimeError):
        media_routes.transcode_video(asset_id, user)

    # A subsequent request must still be able to reserve the single FFmpeg slot.
    assert semaphore.acquire(blocking=False)
    semaphore.release()
