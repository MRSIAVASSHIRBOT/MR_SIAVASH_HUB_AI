from pathlib import Path
from uuid import UUID

import pytest

from mrhub.media.repository import MediaAssetBusy, MediaAssetRepository


def _repository(tmp_path: Path) -> MediaAssetRepository:
    repository = MediaAssetRepository(tmp_path / "db.sqlite3")
    repository.tasks.create_auth_user("owner-1", "owner", "test-salt", "test-hash")
    return repository


def test_deleted_media_file_cleanup_is_durable_and_retryable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = _repository(tmp_path)
    asset = repository.store_upload(
        "owner-1", "sample.png", "image/png", b"test-image-content"
    )
    asset_id = UUID(str(asset["asset_id"]))
    storage_key = str(asset["storage_key"])
    real_file_path = repository.file_path
    stored_path = real_file_path(storage_key)
    assert stored_path.is_file()

    deleted_keys = repository.delete("owner-1", asset_id)
    assert deleted_keys == [storage_key]
    assert repository.get("owner-1", asset_id) is None

    # A fresh repository instance sees the cleanup intent committed by the delete.
    restarted = MediaAssetRepository(repository.database_path)
    real_restarted_path = restarted.file_path
    restarted_path = real_restarted_path(storage_key)
    assert restarted_path.is_file()

    def fail_cleanup(key: str) -> Path:
        if key == storage_key:
            raise PermissionError("simulated filesystem denial")
        return real_restarted_path(key)

    monkeypatch.setattr(restarted, "file_path", fail_cleanup)
    assert restarted.cleanup_pending_files("owner-1") == 1
    assert restarted_path.is_file()

    monkeypatch.setattr(restarted, "file_path", real_restarted_path)
    assert restarted.cleanup_pending_files("owner-1") == 0
    assert not restarted_path.exists()


def test_asset_cannot_be_deleted_while_transcode_is_in_progress(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    asset = repository.store_upload(
        "owner-1", "sample.mp4", "video/mp4", b"fake-mp4-content"
    )
    asset_id = UUID(str(asset["asset_id"]))

    assert repository.begin_processing("owner-1", asset_id) is not None
    with pytest.raises(MediaAssetBusy):
        repository.delete("owner-1", asset_id)

    assert repository.get("owner-1", asset_id) is not None
