import hashlib
import json
import shutil
import sqlite3
from pathlib import Path

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



def test_application_database_backup_restores_owner_login(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from client_helpers import authenticated_client
    from mrhub.config import get_settings
    from mrhub.main import create_app

    original_client = authenticated_client()
    source = get_settings().database_path
    backup = tmp_path / "mrhub-backup.sqlite3"
    restored = tmp_path / "mrhub-restored.sqlite3"

    manifest = backup_database(source, backup)
    assert manifest["sqlite_integrity"] == "ok"
    result = restore_database(backup, restored)
    assert result["restored"] is True

    monkeypatch.setenv("MRH_DATABASE_PATH", str(restored))
    get_settings.cache_clear()
    with TestClient(create_app()) as restored_client:
        login = restored_client.post(
            "/auth/login",
            json={
                "username": "owner",
                "password": "test-only-strong-password-2026",
            },
        )
        assert login.status_code == 200
        token = login.json()["access_token"]
        protected = restored_client.get(
            "/tasks",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert protected.status_code == 200

    original_client.close()
    get_settings.cache_clear()


def test_verify_media_assets_checks_registered_file_size_and_hash_read_only(tmp_path):
    from mrhub.operations.backup import verify_media_assets

    database = tmp_path / "hub.sqlite3"
    media_root = tmp_path / "content_assets"
    media_root.mkdir()
    payload = b"verified media fixture"
    storage_key = "12345678-1234-1234-1234-123456789abc.mp4"
    (media_root / storage_key).write_bytes(payload)
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE content_assets (storage_key TEXT, file_size INTEGER, content_hash TEXT)"
        )
        connection.execute(
            "INSERT INTO content_assets VALUES (?, ?, ?)",
            (storage_key, len(payload), hashlib.sha256(payload).hexdigest()),
        )

    result = verify_media_assets(database)

    assert result == {
        "ok": True,
        "registered_assets": 1,
        "verified_assets": 1,
        "missing_assets": 0,
        "size_mismatched_assets": 0,
        "hash_mismatched_assets": 0,
        "invalid_entries": 0,
        "unregistered_entries": 0,
        "verification_truncated": False,
    }
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM content_assets").fetchone() == (1,)


def test_verify_media_assets_reports_missing_tampered_and_unregistered_files(tmp_path):
    from mrhub.operations.backup import verify_media_assets

    database = tmp_path / "hub.sqlite3"
    media_root = tmp_path / "content_assets"
    media_root.mkdir()
    missing_key = "12345678-1234-1234-1234-123456789abc.mp4"
    changed_key = "22345678-1234-1234-1234-123456789abc.jpg"
    (media_root / changed_key).write_bytes(b"changed")
    (media_root / "unregistered.tmp").write_bytes(b"orphan")
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE content_assets (storage_key TEXT, file_size INTEGER, content_hash TEXT)"
        )
        connection.executemany(
            "INSERT INTO content_assets VALUES (?, ?, ?)",
            [
                (missing_key, 3, "0" * 64),
                (changed_key, 3, "0" * 64),
            ],
        )

    result = verify_media_assets(database)

    assert result["ok"] is False
    assert result["registered_assets"] == 2
    assert result["verified_assets"] == 0
    assert result["missing_assets"] == 1
    assert result["size_mismatched_assets"] == 1
    assert result["hash_mismatched_assets"] == 1
    assert result["unregistered_entries"] == 1


def test_verify_media_assets_rejects_unsafe_storage_key_without_echoing_it(tmp_path):
    from mrhub.operations.backup import verify_media_assets

    database = tmp_path / "hub.sqlite3"
    media_root = tmp_path / "content_assets"
    media_root.mkdir()
    unsafe_key = "../outside.mp4"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE content_assets (storage_key TEXT, file_size INTEGER, content_hash TEXT)"
        )
        connection.execute(
            "INSERT INTO content_assets VALUES (?, ?, ?)",
            (unsafe_key, 1, "0" * 64),
        )

    result = verify_media_assets(database)

    assert result["ok"] is False
    assert result["invalid_entries"] == 1
    assert unsafe_key not in str(result)


def test_verify_media_assets_rejects_symlinked_media_root_even_when_empty(tmp_path):
    from mrhub.operations.backup import verify_media_assets

    database = tmp_path / "hub.sqlite3"
    external_root = tmp_path / "external_assets"
    external_root.mkdir()
    media_root = tmp_path / "content_assets"
    try:
        media_root.symlink_to(external_root, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("Directory symlinks are unavailable in this environment")
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE content_assets (storage_key TEXT, file_size INTEGER, content_hash TEXT)"
        )

    result = verify_media_assets(database)

    assert result["ok"] is False
    assert result["registered_assets"] == 0
    assert result["invalid_entries"] == 1


def test_verify_media_assets_fails_closed_when_registry_exceeds_work_budget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    from mrhub.operations import backup

    database = tmp_path / "hub.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE content_assets (storage_key TEXT, file_size INTEGER, content_hash TEXT)"
        )
        connection.executemany(
            "INSERT INTO content_assets VALUES (?, ?, ?)",
            [
                ("12345678-1234-1234-1234-123456789abc.mp4", 1, "0" * 64),
                ("22345678-1234-1234-1234-123456789abc.mp4", 1, "0" * 64),
            ],
        )
    monkeypatch.setattr(backup, "MAX_MEDIA_ASSETS_TO_VERIFY", 1)

    result = backup.verify_media_assets(database)

    assert result["ok"] is False
    assert result["registered_assets"] == 2
    assert result["verified_assets"] == 0
    assert result["verification_truncated"] is True


def test_verify_media_assets_rejects_implausible_metadata_before_hashing(tmp_path):
    from mrhub.operations.backup import verify_media_assets

    database = tmp_path / "hub.sqlite3"
    media_root = tmp_path / "content_assets"
    media_root.mkdir()
    storage_key = "12345678-1234-1234-1234-123456789abc.mp4"
    (media_root / storage_key).write_bytes(b"payload")
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE content_assets (storage_key TEXT, file_size INTEGER, content_hash TEXT)"
        )
        connection.execute(
            "INSERT INTO content_assets VALUES (?, ?, ?)",
            (storage_key, 100_000_001, "not-a-sha256"),
        )

    result = verify_media_assets(database)

    assert result["ok"] is False
    assert result["invalid_entries"] == 1
    assert result["verified_assets"] == 0


def test_verify_media_assets_bounds_unregistered_directory_scan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    from mrhub.operations import backup

    database = tmp_path / "hub.sqlite3"
    media_root = tmp_path / "content_assets"
    media_root.mkdir()
    (media_root / "orphan-one").write_bytes(b"x")
    (media_root / "orphan-two").write_bytes(b"x")
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE content_assets (storage_key TEXT, file_size INTEGER, content_hash TEXT)"
        )
    monkeypatch.setattr(backup, "MAX_MEDIA_ASSETS_TO_VERIFY", 1)

    result = backup.verify_media_assets(database)

    assert result["ok"] is False
    assert result["verification_truncated"] is True


def test_verify_media_assets_does_not_hash_files_over_per_asset_limit(tmp_path, monkeypatch):
    from mrhub.operations import backup

    database = tmp_path / "hub.sqlite3"
    media_root = tmp_path / "content_assets"
    media_root.mkdir()
    storage_key = "12345678-1234-1234-1234-123456789abc.mp4"
    (media_root / storage_key).write_bytes(b"payload-too-large")
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE content_assets (storage_key TEXT, file_size INTEGER, content_hash TEXT)"
        )
        connection.execute(
            "INSERT INTO content_assets VALUES (?, ?, ?)",
            (storage_key, 7, "0" * 64),
        )
    monkeypatch.setattr(backup, "MAX_MEDIA_ASSET_BYTES", 4)

    result = backup.verify_media_assets(database)

    assert result["ok"] is False
    assert result["invalid_entries"] == 1
    assert result["hash_mismatched_assets"] == 0



def test_clean_destination_restore_recovers_database_and_media_asset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    from fastapi.testclient import TestClient

    from mrhub.config import get_settings
    from mrhub.main import create_app
    from mrhub.operations.backup import verify_media_assets

    source_dir = tmp_path / "source"
    source_dir.mkdir()
    source_database = source_dir / "hub.sqlite3"
    monkeypatch.setenv("MRH_DATABASE_PATH", str(source_database))
    monkeypatch.setenv(
        "MRH_WORKFLOW_PAYLOAD_KEY",
        "dGVzdC1vbmx5LXBheWxvYWQta2V5LTMyLWJ5dGVzISE=",
    )
    get_settings.cache_clear()

    media_payload = b"\\x89PNG\\r\\n\\x1a\\nrecovery-fixture"
    with TestClient(create_app()) as source_client:
        setup = source_client.post(
            "/auth/setup",
            json={"password": "test-only-strong-password-2026"},
        )
        assert setup.status_code == 201
        login = source_client.post(
            "/auth/login",
            json={
                "username": "owner",
                "password": "test-only-strong-password-2026",
            },
        )
        assert login.status_code == 200
        source_headers = {
            "Authorization": f"Bearer {login.json()['access_token']}",
            "X-File-Name": "recovery.png",
            "Content-Type": "image/png",
        }
        uploaded = source_client.post(
            "/content/assets",
            headers=source_headers,
            content=media_payload,
        )
        assert uploaded.status_code == 201
        asset_id = uploaded.json()["asset_id"]

    backup = tmp_path / "recovery.sqlite3"
    manifest = backup_database(source_database, backup)
    assert manifest["sqlite_integrity"] == "ok"

    restored_dir = tmp_path / "restored"
    restored_database = restored_dir / "hub.sqlite3"
    result = restore_database(backup, restored_database)
    assert result["restored"] is True
    shutil.copytree(source_dir / "content_assets", restored_dir / "content_assets")

    verification = verify_media_assets(restored_database)
    assert verification["ok"] is True
    assert verification["registered_assets"] == 1
    assert verification["verified_assets"] == 1

    monkeypatch.setenv("MRH_DATABASE_PATH", str(restored_database))
    get_settings.cache_clear()
    with TestClient(create_app()) as restored_client:
        login = restored_client.post(
            "/auth/login",
            json={
                "username": "owner",
                "password": "test-only-strong-password-2026",
            },
        )
        assert login.status_code == 200
        restored_headers = {
            "Authorization": f"Bearer {login.json()['access_token']}"
        }
        assets = restored_client.get(
            "/content/assets", headers=restored_headers
        )
        assert assets.status_code == 200
        assert assets.json()["count"] == 1
        assert assets.json()["assets"][0]["asset_id"] == asset_id

        download = restored_client.get(
            f"/content/assets/{asset_id}/file",
            headers=restored_headers,
        )
        assert download.status_code == 200
        assert download.content == media_payload

    get_settings.cache_clear()
