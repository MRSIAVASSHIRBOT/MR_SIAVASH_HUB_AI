import json
import sqlite3

import pytest

from mrhub.operations.backup import BackupError, backup_database, restore_database


def make_database(path):
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE records (id INTEGER PRIMARY KEY, value TEXT NOT NULL)")
        connection.execute("INSERT INTO records(value) VALUES ('preserve me')")


def test_backup_and_restore_verify_checksum_and_preserve_database(tmp_path):
    source = tmp_path / "source.sqlite3"
    backup = tmp_path / "backup.sqlite3"
    restored = tmp_path / "restored.sqlite3"
    make_database(source)

    manifest = backup_database(source, backup)
    assert manifest["sqlite_integrity"] == "ok"
    assert manifest["included"] == ["sqlite_database"]
    assert "provider_tokens" in manifest["excluded"]

    result = restore_database(backup, restored)
    assert result["restored"] is True
    assert result["destination_overwritten"] is False
    with sqlite3.connect(restored) as connection:
        assert connection.execute("SELECT value FROM records").fetchone() == ("preserve me",)


def test_backup_refuses_to_overwrite_existing_destination(tmp_path):
    source = tmp_path / "source.sqlite3"
    destination = tmp_path / "backup.sqlite3"
    make_database(source)
    destination.write_bytes(b"existing")

    with pytest.raises(BackupError, match="already exists"):
        backup_database(source, destination)
    assert destination.read_bytes() == b"existing"


def test_restore_rejects_modified_backup(tmp_path):
    source = tmp_path / "source.sqlite3"
    backup = tmp_path / "backup.sqlite3"
    restored = tmp_path / "restored.sqlite3"
    make_database(source)
    backup_database(source, backup)

    with backup.open("ab") as stream:
        stream.write(b"tampered")

    with pytest.raises(BackupError, match="checksum"):
        restore_database(backup, restored)
    assert not restored.exists()


def test_restore_requires_valid_manifest(tmp_path):
    source = tmp_path / "source.sqlite3"
    backup = tmp_path / "backup.sqlite3"
    make_database(source)
    backup_database(source, backup)
    manifest_path = backup.with_suffix(".sqlite3.manifest.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["sha256"] = "0" * 64
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(BackupError, match="checksum"):
        restore_database(backup, tmp_path / "restored.sqlite3")
