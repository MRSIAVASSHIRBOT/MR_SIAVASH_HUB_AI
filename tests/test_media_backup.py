import hashlib
import json
import sqlite3

import pytest

from mrhub.operations.backup import (
    BackupError,
    backup_media_assets,
    main,
    restore_media_assets,
    verify_media_backup,
)


def make_media_database(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    database = tmp_path / "hub.sqlite3"
    media_root = tmp_path / "content_assets"
    media_root.mkdir()
    records = {
        "12345678-1234-4234-8234-123456789abc.mp4": b"sample-video-content",
        "abcdefab-cdef-4abc-8def-abcdefabcdef.jpg": b"sample-image-content",
    }
    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            CREATE TABLE content_assets (
                storage_key TEXT,
                file_size INTEGER,
                content_hash TEXT
            )
            """
        )
        for storage_key, payload in records.items():
            (media_root / storage_key).write_bytes(payload)
            connection.execute(
                "INSERT INTO content_assets VALUES (?, ?, ?)",
                (storage_key, len(payload), hashlib.sha256(payload).hexdigest()),
            )
    return database, records


def test_media_backup_verification_and_restore_round_trip(tmp_path):
    database, records = make_media_database(tmp_path)
    backup = tmp_path / "media-backup"
    restored = tmp_path / "restored-media"

    created = backup_media_assets(database, backup)
    assert created["ok"] is True
    assert created["asset_count"] == len(records)
    assert created["total_bytes"] == sum(map(len, records.values()))

    verified = verify_media_backup(backup)
    assert verified["ok"] is True
    assert verified["verified_assets"] == len(records)

    restored_result = restore_media_assets(backup, restored)
    assert restored_result["restored"] is True
    assert restored_result["destination_overwritten"] is False
    assert not (restored / "manifest.json").exists()
    for storage_key, payload in records.items():
        assert (restored / storage_key).read_bytes() == payload


def test_media_backup_refuses_corrupt_source_and_size_limit(tmp_path):
    database, records = make_media_database(tmp_path)
    storage_key = next(iter(records))
    (tmp_path / "content_assets" / storage_key).write_bytes(b"changed")
    destination = tmp_path / "should-not-exist"

    with pytest.raises(BackupError, match="source failed integrity"):
        backup_media_assets(database, destination)
    assert not destination.exists()

    database, _ = make_media_database(tmp_path / "second")
    with pytest.raises(BackupError, match="size limit"):
        backup_media_assets(database, tmp_path / "too-large", max_total_bytes=1)
    assert not (tmp_path / "too-large").exists()


def test_media_backup_detects_tampering_and_restore_never_overwrites(tmp_path):
    database, records = make_media_database(tmp_path)
    backup = tmp_path / "media-backup"
    backup_media_assets(database, backup)

    storage_key = next(iter(records))
    (backup / "content_assets" / storage_key).write_bytes(b"x" * len(records[storage_key]))
    verification = verify_media_backup(backup)
    assert verification["ok"] is False
    assert verification["hash_mismatched_assets"] == 1

    rejected_restore = tmp_path / "rejected-restore"
    with pytest.raises(BackupError, match="integrity verification"):
        restore_media_assets(backup, rejected_restore)
    assert not rejected_restore.exists()

    valid_backup = tmp_path / "valid-media-backup"
    backup_media_assets(database, valid_backup)
    existing = tmp_path / "existing-media"
    existing.mkdir()
    sentinel = existing / "keep.txt"
    sentinel.write_text("keep", encoding="utf-8")
    with pytest.raises(BackupError):
        restore_media_assets(valid_backup, existing)
    assert sentinel.read_text(encoding="utf-8") == "keep"


def test_media_backup_cli_exposes_machine_readable_recovery_commands(tmp_path, capsys):
    database, records = make_media_database(tmp_path)
    backup = tmp_path / "cli-media-backup"
    restored = tmp_path / "cli-restored-media"

    assert main(["backup-media", str(database), str(backup)]) == 0
    created = json.loads(capsys.readouterr().out)
    assert created["ok"] is True
    assert created["asset_count"] == len(records)

    assert main(["verify-media-backup", str(backup)]) == 0
    verified = json.loads(capsys.readouterr().out)
    assert verified["ok"] is True

    assert main(["restore-media", str(backup), str(restored)]) == 0
    restored_result = json.loads(capsys.readouterr().out)
    assert restored_result["restored"] is True
    assert all((restored / key).is_file() for key in records)



def test_media_backup_refuses_existing_destination_and_reports_orphan_files(tmp_path):
    database, _ = make_media_database(tmp_path)
    existing = tmp_path / "existing-backup"
    existing.mkdir()
    sentinel = existing / "keep.txt"
    sentinel.write_text("keep", encoding="utf-8")

    with pytest.raises(BackupError):
        backup_media_assets(database, existing)
    assert sentinel.read_text(encoding="utf-8") == "keep"

    backup = tmp_path / "verified-backup"
    backup_media_assets(database, backup)
    orphan = backup / "content_assets" / "orphan.bin"
    orphan.write_bytes(b"unregistered")
    result = verify_media_backup(backup)
    assert result["ok"] is False
    assert result["unregistered_entries"] == 1
