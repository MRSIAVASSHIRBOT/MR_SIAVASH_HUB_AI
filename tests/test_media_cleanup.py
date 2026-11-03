from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from uuid import UUID

import pytest

from mrhub.media.repository import (
    MediaAssetBusy,
    MediaAssetOwnershipConflict,
    MediaAssetRepository,
)


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


def test_deleting_transcoded_derivative_queues_its_file_for_cleanup(
    tmp_path: Path,
) -> None:
    repository = _repository(tmp_path)
    source = repository.store_upload(
        "owner-1", "source.mp4", "video/mp4", b"fake-source-video"
    )
    source_id = UUID(str(source["asset_id"]))
    assert repository.begin_processing("owner-1", source_id) is not None

    output_id, output_key, output_path = repository.new_output_target()
    output_path.write_bytes(b"fake-transcoded-video")
    repository.register_transcoded_output(
        "owner-1",
        source_id,
        output_id,
        output_key,
        output_path,
        "source-processed.mp4",
    )

    deleted_keys = repository.delete("owner-1", UUID(output_id))

    assert deleted_keys == [output_key]
    assert repository.get("owner-1", UUID(output_id)) is None
    restored_source = repository.get("owner-1", source_id)
    assert restored_source is not None
    assert restored_source["processing_status"] == "stored"
    assert repository.cleanup_pending_files("owner-1") == 0
    assert not output_path.exists()


def test_deleting_source_queues_source_and_derivative_files(
    tmp_path: Path,
) -> None:
    repository = _repository(tmp_path)
    source = repository.store_upload(
        "owner-1", "source.mp4", "video/mp4", b"fake-source-video"
    )
    source_id = UUID(str(source["asset_id"]))
    assert repository.begin_processing("owner-1", source_id) is not None

    output_id, output_key, output_path = repository.new_output_target()
    output_path.write_bytes(b"fake-transcoded-video")
    repository.register_transcoded_output(
        "owner-1",
        source_id,
        output_id,
        output_key,
        output_path,
        "source-processed.mp4",
    )
    source_path = repository.file_path(str(source["storage_key"]))
    assert source_path.is_file()
    assert output_path.is_file()

    deleted_keys = repository.delete("owner-1", source_id)

    assert set(deleted_keys) == {str(source["storage_key"]), output_key}
    assert repository.get("owner-1", source_id) is None
    assert repository.get("owner-1", UUID(output_id)) is None
    assert repository.cleanup_pending_files("owner-1") == 0
    assert not source_path.exists()
    assert not output_path.exists()


def test_source_cleanup_query_is_scoped_to_asset_owner(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    repository.tasks.create_auth_user("owner-2", "other", "test-salt", "test-hash")
    source = repository.store_upload(
        "owner-1", "source.mp4", "video/mp4", b"fake-source-video"
    )
    source_id = UUID(str(source["asset_id"]))
    foreign_id, foreign_key, foreign_path = repository.new_output_target()
    foreign_path.write_bytes(b"foreign-file")
    now = repository._now()
    with repository.tasks._connection() as connection:
        connection.execute(
            """
            INSERT INTO content_assets (
                asset_id, owner_user_id, source_asset_id, original_filename,
                media_type, storage_key, file_size, content_hash,
                processing_status, processing_profile, error_code, created_at, updated_at
            ) VALUES (?, ?, ?, ?, 'video/mp4', ?, ?, ?, 'processed',
                      'video_mp4_720p', NULL, ?, ?)
            """,
            (
                foreign_id, "owner-2", str(source_id), "foreign.mp4",
                foreign_key, len(b"foreign-file"),
                "0" * 64, now, now,
            ),
        )

    source_path = repository.file_path(str(source["storage_key"]))
    foreign_asset_id = UUID(foreign_id)

    with pytest.raises(MediaAssetOwnershipConflict):
        repository.delete("owner-1", source_id)

    # The transaction must roll back before ON DELETE CASCADE can remove another
    # owner's derivative metadata or enqueue its storage key for the wrong owner.
    assert repository.get("owner-1", source_id) is not None
    assert repository.get("owner-2", foreign_asset_id) is not None
    assert source_path.is_file()
    assert foreign_path.is_file()
    assert repository.cleanup_pending_files("owner-1") == 0
    assert repository.cleanup_pending_files("owner-2") == 0


def test_cleanup_queue_is_owner_scoped_and_idempotent(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    repository.tasks.create_auth_user("owner-2", "other", "test-salt", "test-hash")
    asset = repository.store_upload(
        "owner-1", "sample.png", "image/png", b"test-image-content"
    )
    asset_id = UUID(str(asset["asset_id"]))
    path = repository.file_path(str(asset["storage_key"]))

    assert repository.delete("owner-1", asset_id) == [str(asset["storage_key"])]
    assert repository.delete("owner-1", asset_id) is None

    # A different owner cannot drain this owner's cleanup queue.
    assert repository.cleanup_pending_files("owner-2") == 0
    assert path.is_file()
    assert repository.cleanup_pending_files("owner-1") == 0
    assert not path.exists()
    assert repository.cleanup_pending_files("owner-1") == 0


def test_delete_and_begin_processing_are_serialized(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    asset = repository.store_upload(
        "owner-1", "sample.mp4", "video/mp4", b"fake-mp4-content"
    )
    asset_id = UUID(str(asset["asset_id"]))
    storage_key = str(asset["storage_key"])
    path = repository.file_path(storage_key)
    barrier = Barrier(2)

    def begin_processing():
        barrier.wait()
        return repository.begin_processing("owner-1", asset_id)

    def delete_asset():
        barrier.wait()
        try:
            return ("deleted", repository.delete("owner-1", asset_id))
        except MediaAssetBusy:
            return ("busy", None)

    with ThreadPoolExecutor(max_workers=2) as executor:
        processing_future = executor.submit(begin_processing)
        deletion_future = executor.submit(delete_asset)
        processing = processing_future.result(timeout=10)
        deletion_status, deleted_keys = deletion_future.result(timeout=10)

    if processing is not None:
        assert deletion_status == "busy"
        assert repository.get("owner-1", asset_id) is not None
        assert path.is_file()
        assert repository.cleanup_pending_files("owner-1") == 0
    else:
        assert deletion_status == "deleted"
        assert deleted_keys == [storage_key]
        assert repository.get("owner-1", asset_id) is None
        assert repository.cleanup_pending_files("owner-1") == 0
        assert not path.exists()
