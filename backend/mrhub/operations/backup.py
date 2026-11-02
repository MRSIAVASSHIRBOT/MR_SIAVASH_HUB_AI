"""Verified local SQLite backup/restore primitives; key material and media stay separate."""

from __future__ import annotations

import hashlib
import json
import os
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
        os.replace(temporary_path, destination_path)
        temporary_path = None
        os.replace(temporary_manifest, manifest_path)
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
        os.replace(temporary_path, destination_path)
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
