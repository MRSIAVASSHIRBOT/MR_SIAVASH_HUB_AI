"""Verified local SQLite backup/restore primitives; key material and media stay separate."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import tempfile
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class BackupError(RuntimeError):
    """Raised when a backup cannot be created or safely restored."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _private_permissions(path: Path) -> None:
    if os.name == "posix":
        path.chmod(0o600)


def _quick_check(path: Path) -> None:
    try:
        with closing(sqlite3.connect(path)) as connection:
            rows = connection.execute("PRAGMA quick_check").fetchall()
    except sqlite3.Error as exc:
        raise BackupError("SQLite integrity check could not run") from exc
    if rows != [("ok",)]:
        raise BackupError("SQLite integrity check failed")


def backup_database(source: str | Path, destination: str | Path) -> dict[str, Any]:
    """Create a consistent SQLite backup and checksum manifest without overwriting files."""
    source_path = Path(source).expanduser().resolve(strict=True)
    destination_path = Path(destination).expanduser().absolute()
    manifest_path = destination_path.with_suffix(destination_path.suffix + ".manifest.json")
    if not source_path.is_file():
        raise BackupError("Backup source must be a regular file")
    if source_path == destination_path:
        raise BackupError("Backup destination must differ from source")
    if destination_path.exists() or manifest_path.exists():
        raise BackupError("Backup destination or manifest already exists")
    destination_path.parent.mkdir(parents=True, exist_ok=True)

    temporary_path: Path | None = None
    temporary_manifest: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix=".mrhub-backup-", suffix=".sqlite3", dir=destination_path.parent, delete=False
        ) as temporary:
            temporary_path = Path(temporary.name)
        with closing(sqlite3.connect(source_path)) as source_connection, closing(
            sqlite3.connect(temporary_path)
        ) as backup_connection:
            source_connection.backup(backup_connection)
            backup_connection.commit()
        _quick_check(temporary_path)
        _private_permissions(temporary_path)
        manifest = {
            "format_version": 1,
            "created_at": datetime.now(UTC).isoformat(),
            "source_name": source_path.name,
            "backup_name": destination_path.name,
            "byte_size": temporary_path.stat().st_size,
            "sha256": _sha256(temporary_path),
            "sqlite_integrity": "ok",
            "included": ["sqlite_database"],
            "excluded": ["application_secrets", "provider_tokens", "external_media"],
        }
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", prefix=".mrhub-manifest-", suffix=".json",
            dir=destination_path.parent, delete=False
        ) as temporary:
            temporary_manifest = Path(temporary.name)
            json.dump(manifest, temporary, ensure_ascii=False, sort_keys=True, indent=2)
            temporary.write("\n")
            temporary.flush()
            os.fsync(temporary.fileno())
        _private_permissions(temporary_manifest)
        # Hard-link publication is atomic and fails if a destination appeared after
        # the preflight check; unlike os.replace, it cannot overwrite an existing file.
        os.link(temporary_path, destination_path)
        published_backup = destination_path.stat()
        temporary_path.unlink()
        temporary_path = None
        try:
            os.link(temporary_manifest, manifest_path)
        except OSError:
            # Remove only the file we created, and only if it is still the same inode.
            current = destination_path.stat()
            if (current.st_dev, current.st_ino) == (published_backup.st_dev, published_backup.st_ino):
                destination_path.unlink(missing_ok=True)
            raise
        temporary_manifest.unlink()
        temporary_manifest = None
        return manifest
    except (OSError, sqlite3.Error) as exc:
        raise BackupError("Backup creation failed; destination was not intentionally overwritten") from exc
    finally:
        for path in (temporary_path, temporary_manifest):
            if path is not None:
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    pass


_MEDIA_STORAGE_KEY_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\.(?:mp4|mov|jpg|png|webp|mp3|wav)$"
)

MAX_MEDIA_ASSETS_TO_VERIFY = 10_000
MAX_MEDIA_ASSET_BYTES = 100_000_000


def verify_media_assets(database: str | Path) -> dict[str, Any]:
    """Read-only verification of registered media files against SQLite metadata.

    The verifier never copies, deletes, follows symlinks, or returns storage keys.
    Stop API/worker writers before using it as a backup consistency gate.
    """
    database_path = Path(database).expanduser().resolve(strict=True)
    if not database_path.is_file():
        raise BackupError("Media verification source must be a regular database file")
    media_root = database_path.parent / "content_assets"
    try:
        with closing(
            sqlite3.connect(f"{database_path.as_uri()}?mode=ro", uri=True)
        ) as connection:
            count_row = connection.execute(
                "SELECT COUNT(*) FROM content_assets"
            ).fetchone()
            registered_asset_count = int(count_row[0]) if count_row else 0
            rows = (
                connection.execute(
                    "SELECT storage_key, file_size, content_hash FROM content_assets "
                    "ORDER BY storage_key LIMIT ?",
                    (MAX_MEDIA_ASSETS_TO_VERIFY + 1,),
                ).fetchall()
                if registered_asset_count <= MAX_MEDIA_ASSETS_TO_VERIFY
                else []
            )
    except sqlite3.Error as exc:
        raise BackupError("Media asset registry could not be read") from exc

    result: dict[str, Any] = {
        "ok": True,
        "registered_assets": registered_asset_count,
        "verified_assets": 0,
        "missing_assets": 0,
        "size_mismatched_assets": 0,
        "hash_mismatched_assets": 0,
        "invalid_entries": 0,
        "unregistered_entries": 0,
        "verification_truncated": registered_asset_count > MAX_MEDIA_ASSETS_TO_VERIFY,
    }
    registered_keys: set[str] = set()
    root_is_safe = not media_root.is_symlink()
    if not root_is_safe:
        result["invalid_entries"] += 1
    try:
        resolved_root = media_root.resolve(strict=False)
    except OSError:
        resolved_root = media_root.absolute()
        root_is_safe = False

    for storage_key, expected_size, expected_hash in rows:
        key = storage_key if isinstance(storage_key, str) else ""
        if not _MEDIA_STORAGE_KEY_PATTERN.fullmatch(key):
            result["invalid_entries"] += 1
            continue
        if not root_is_safe:
            continue
        registered_keys.add(key)
        try:
            bounded_expected_size = int(expected_size)
        except (TypeError, ValueError):
            result["invalid_entries"] += 1
            continue
        if (
            bounded_expected_size < 0
            or bounded_expected_size > MAX_MEDIA_ASSET_BYTES
            or not isinstance(expected_hash, str)
            or not re.fullmatch(r"[0-9a-f]{64}", expected_hash)
        ):
            result["invalid_entries"] += 1
            continue
        candidate = media_root / key
        try:
            if candidate.is_symlink():
                result["invalid_entries"] += 1
                continue
            resolved = candidate.resolve(strict=True)
        except FileNotFoundError:
            result["missing_assets"] += 1
            continue
        except OSError:
            result["invalid_entries"] += 1
            continue
        if resolved.parent != resolved_root or not resolved.is_file():
            result["invalid_entries"] += 1
            continue

        valid = True
        try:
            if resolved.stat().st_size != bounded_expected_size:
                result["size_mismatched_assets"] += 1
                valid = False
            if _sha256(resolved) != expected_hash:
                result["hash_mismatched_assets"] += 1
                valid = False
        except (OSError, TypeError, ValueError):
            result["invalid_entries"] += 1
            continue
        if valid:
            result["verified_assets"] += 1

    if media_root.exists() and root_is_safe:
        try:
            for entry in media_root.iterdir():
                if entry.name not in registered_keys:
                    result["unregistered_entries"] += 1
        except OSError:
            result["invalid_entries"] += 1

    result["ok"] = not result["verification_truncated"] and all(
        result[key] == 0
        for key in (
            "missing_assets",
            "size_mismatched_assets",
            "hash_mismatched_assets",
            "invalid_entries",
            "unregistered_entries",
        )
    )
    return result


def restore_database(backup: str | Path, destination: str | Path) -> dict[str, Any]:
    """Verify the backup manifest and SQLite integrity before atomically restoring a new file."""
    backup_path = Path(backup).expanduser().resolve(strict=True)
    destination_path = Path(destination).expanduser().absolute()
    manifest_path = backup_path.with_suffix(backup_path.suffix + ".manifest.json")
    if not backup_path.is_file():
        raise BackupError("Restore source must be a regular file")
    if backup_path == destination_path:
        raise BackupError("Restore destination must differ from backup")
    if destination_path.exists():
        raise BackupError("Restore destination already exists")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BackupError("Backup manifest is missing or invalid") from exc
    if (
        not isinstance(manifest, dict)
        or manifest.get("format_version") != 1
        or manifest.get("sha256") != _sha256(backup_path)
        or manifest.get("byte_size") != backup_path.stat().st_size
    ):
        raise BackupError("Backup checksum or manifest validation failed")
    _quick_check(backup_path)
    destination_path.parent.mkdir(parents=True, exist_ok=True)

    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix=".mrhub-restore-", suffix=".sqlite3", dir=destination_path.parent, delete=False
        ) as temporary:
            temporary_path = Path(temporary.name)
        with closing(sqlite3.connect(backup_path)) as backup_connection, closing(
            sqlite3.connect(temporary_path)
        ) as destination_connection:
            backup_connection.backup(destination_connection)
            destination_connection.commit()
        _quick_check(temporary_path)
        _private_permissions(temporary_path)
        # Atomic no-clobber publication: refuse a destination created after preflight.
        os.link(temporary_path, destination_path)
        temporary_path.unlink()
        temporary_path = None
        return {
            "restored": True,
            "destination_name": destination_path.name,
            "sha256": _sha256(destination_path),
            "sqlite_integrity": "ok",
            "destination_overwritten": False,
        }
    except (OSError, sqlite3.Error) as exc:
        raise BackupError("Restore failed; destination was not intentionally overwritten") from exc
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass
