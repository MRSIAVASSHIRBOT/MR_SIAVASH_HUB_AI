from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Barrier
from uuid import UUID, uuid4

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



def test_failed_cleanup_items_do_not_starve_unattempted_entries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = _repository(tmp_path)
    now = datetime(2026, 11, 3, tzinfo=UTC)
    keys = [f"{uuid4()}.png" for _ in range(101)]
    with repository.tasks._connection() as connection:
        for index, key in enumerate(keys):
            repository.file_path(key).write_bytes(b"queued-file")
            created_at = (now + timedelta(microseconds=index)).isoformat()
            connection.execute(
                """
                INSERT INTO media_file_cleanup (
                    cleanup_id, owner_user_id, storage_key, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (str(uuid4()), "owner-1", key, created_at, created_at),
            )

    with repository.tasks._connection() as connection:
        first_batch = {
            row["storage_key"]
            for row in connection.execute(
                "SELECT storage_key FROM media_file_cleanup "
                "WHERE owner_user_id = ? ORDER BY created_at LIMIT 100",
                ("owner-1",),
            ).fetchall()
        }
    untouched_key = next(key for key in keys if key not in first_batch)
    real_file_path = repository.file_path

    def fail_first_batch(key: str) -> Path:
        if key in first_batch:
            raise PermissionError("simulated persistent filesystem denial")
        return real_file_path(key)

    monkeypatch.setattr(repository, "file_path", fail_first_batch)

    assert repository.cleanup_pending_files("owner-1", limit=100) == 101
    assert real_file_path(untouched_key).is_file()

    # The unattempted item has attempt_count=0 and must be selected before
    # the 100 repeatedly failing items on the next bounded pass.
    assert repository.cleanup_pending_files("owner-1", limit=100) == 100
    assert not real_file_path(untouched_key).exists()



def _active_worker_lease(repository: MediaAssetRepository, token: int = 1):
    from mrhub.domain.tasks import RiskClass, TaskRecord
    from mrhub.jobs.leases import WorkerLease

    task = TaskRecord(
        task_type="video.analysis",
        risk_class=RiskClass.LOW,
        description="test asset analysis lease",
    )
    repository.tasks.create(task)
    expires_at = (datetime.now(UTC) + timedelta(minutes=5)).isoformat()
    with repository.tasks._connection() as connection:
        connection.execute(
            """INSERT INTO worker_executions (
                task_id, lease_owner, lease_expires_at, execution_token
            ) VALUES (?, ?, ?, ?)""",
            (str(task.task_id), "worker-test", expires_at, token),
        )
    return WorkerLease(
        task_id=str(task.task_id),
        owner="worker-test",
        fencing_token=token,
        expires_at=expires_at,
    )


def test_active_video_analysis_use_blocks_asset_delete_until_release(tmp_path: Path):
    repository = _repository(tmp_path)
    asset = repository.store_upload(
        "owner-1", "analysis.mp4", "video/mp4", b"video-analysis-fixture"
    )
    asset_id = UUID(str(asset["asset_id"]))
    path = repository.file_path(str(asset["storage_key"]))
    lease = _active_worker_lease(repository)

    assert repository.acquire_analysis_use("owner-1", asset_id, lease=lease) is True
    with pytest.raises(MediaAssetBusy, match="video analysis"):
        repository.delete("owner-1", asset_id)

    assert repository.get("owner-1", asset_id) is not None
    assert path.is_file()

    assert repository.release_analysis_use("owner-1", asset_id, lease=lease) is True
    assert repository.delete("owner-1", asset_id) == [str(asset["storage_key"])]
    assert repository.cleanup_pending_files("owner-1") == 0
    assert not path.exists()


def test_analysis_use_lock_is_fenced_by_the_current_worker_execution_token(
    tmp_path: Path,
):
    repository = _repository(tmp_path)
    asset = repository.store_upload(
        "owner-1", "analysis.mp4", "video/mp4", b"video-analysis-fixture"
    )
    asset_id = UUID(str(asset["asset_id"]))
    path = repository.file_path(str(asset["storage_key"]))
    lease = _active_worker_lease(repository, token=2)

    # A stale lock from a previous attempt must not block deletion after the
    # worker execution has advanced to a different fencing token.
    with repository.tasks._connection() as connection:
        connection.execute(
            """INSERT INTO media_asset_analysis_leases (
                lease_id, asset_id, owner_user_id, task_id,
                lease_owner, execution_token, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                str(uuid4()), str(asset_id), "owner-1", lease.task_id,
                "worker-old", 1, repository._now(),
            ),
        )

    assert repository.delete("owner-1", asset_id) == [str(asset["storage_key"])]
    assert repository.get("owner-1", asset_id) is None
    assert repository.cleanup_pending_files("owner-1") == 0
    assert not path.exists()


def test_expired_worker_lease_does_not_block_video_asset_delete(tmp_path: Path):
    repository = _repository(tmp_path)
    asset = repository.store_upload(
        "owner-1", "analysis.mp4", "video/mp4", b"video-analysis-fixture"
    )
    asset_id = UUID(str(asset["asset_id"]))
    path = repository.file_path(str(asset["storage_key"]))
    lease = _active_worker_lease(repository)

    assert repository.acquire_analysis_use("owner-1", asset_id, lease=lease) is True
    expired_at = (datetime.now(UTC) - timedelta(minutes=1)).isoformat()
    with repository.tasks._connection() as connection:
        connection.execute(
            "UPDATE worker_executions SET lease_expires_at = ? WHERE task_id = ?",
            (expired_at, lease.task_id),
        )

    assert repository.delete("owner-1", asset_id) == [str(asset["storage_key"])]
    assert repository.get("owner-1", asset_id) is None
    assert repository.cleanup_pending_files("owner-1") == 0
    assert not path.exists()


def test_deleting_source_is_blocked_when_its_derivative_is_under_analysis(
    tmp_path: Path,
):
    repository = _repository(tmp_path)
    source = repository.store_upload(
        "owner-1", "source.mp4", "video/mp4", b"fake-source-video"
    )
    source_id = UUID(str(source["asset_id"]))
    assert repository.begin_processing("owner-1", source_id) is not None

    output_id, output_key, output_path = repository.new_output_target()
    output_path.write_bytes(b"fake-transcoded-video")
    repository.register_transcoded_output(
        "owner-1", source_id, output_id, output_key, output_path, "source-processed.mp4"
    )
    lease = _active_worker_lease(repository)
    derivative_id = UUID(output_id)

    assert repository.acquire_analysis_use("owner-1", derivative_id, lease=lease) is True
    with pytest.raises(MediaAssetBusy, match="video analysis"):
        repository.delete("owner-1", source_id)

    assert repository.get("owner-1", source_id) is not None
    assert repository.get("owner-1", derivative_id) is not None
    assert output_path.is_file()


def test_delete_and_analysis_use_acquisition_are_serialized(tmp_path: Path):
    repository = _repository(tmp_path)
    asset = repository.store_upload(
        "owner-1", "analysis.mp4", "video/mp4", b"video-analysis-fixture"
    )
    asset_id = UUID(str(asset["asset_id"]))
    path = repository.file_path(str(asset["storage_key"]))
    lease = _active_worker_lease(repository)
    barrier = Barrier(2)

    def acquire():
        barrier.wait()
        return repository.acquire_analysis_use("owner-1", asset_id, lease=lease)

    def delete_asset():
        barrier.wait()
        try:
            return ("deleted", repository.delete("owner-1", asset_id))
        except MediaAssetBusy:
            return ("busy", None)

    with ThreadPoolExecutor(max_workers=2) as executor:
        acquire_future = executor.submit(acquire)
        delete_future = executor.submit(delete_asset)
        acquired = acquire_future.result(timeout=10)
        delete_status, deleted_keys = delete_future.result(timeout=10)

    if acquired:
        assert delete_status == "busy"
        assert repository.get("owner-1", asset_id) is not None
        assert path.is_file()
        assert repository.release_analysis_use("owner-1", asset_id, lease=lease) is True
    else:
        assert delete_status == "deleted"
        assert deleted_keys == [str(asset["storage_key"])]
        assert repository.get("owner-1", asset_id) is None
        assert repository.cleanup_pending_files("owner-1") == 0
        assert not path.exists()



def test_begin_processing_is_blocked_while_video_analysis_use_is_active(
    tmp_path: Path,
) -> None:
    repository = _repository(tmp_path)
    asset = repository.store_upload(
        "owner-1", "analysis.mp4", "video/mp4", b"video-analysis-fixture"
    )
    asset_id = UUID(str(asset["asset_id"]))
    lease = _active_worker_lease(repository)

    assert repository.acquire_analysis_use("owner-1", asset_id, lease=lease) is True
    assert repository.begin_processing("owner-1", asset_id) is None
    assert repository.get("owner-1", asset_id)["processing_status"] == "stored"

    assert repository.release_analysis_use("owner-1", asset_id, lease=lease) is True
    assert repository.begin_processing("owner-1", asset_id) is not None
