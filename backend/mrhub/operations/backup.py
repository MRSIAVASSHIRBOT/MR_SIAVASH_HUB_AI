"""Verified local SQLite backup/restore primitives; key material and media stay separate."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import sys
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
        with (
            closing(sqlite3.connect(source_path)) as source_connection,
            closing(sqlite3.connect(temporary_path)) as backup_connection,
        ):
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
            mode="w",
            encoding="utf-8",
            prefix=".mrhub-manifest-",
            suffix=".json",
            dir=destination_path.parent,
            delete=False,
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
            if (current.st_dev, current.st_ino) == (
                published_backup.st_dev,
                published_backup.st_ino,
            ):
                destination_path.unlink(missing_ok=True)
            raise
        temporary_manifest.unlink()
        temporary_manifest = None
        return manifest
    except (OSError, sqlite3.Error) as exc:
        raise BackupError(
            "Backup creation failed; destination was not intentionally overwritten"
        ) from exc
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
        with closing(sqlite3.connect(f"{database_path.as_uri()}?mode=ro", uri=True)) as connection:
            count_row = connection.execute("SELECT COUNT(*) FROM content_assets").fetchone()
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
            actual_size = resolved.stat().st_size
            if actual_size > MAX_MEDIA_ASSET_BYTES:
                result["invalid_entries"] += 1
                continue
            if actual_size != bounded_expected_size:
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

    if not result["verification_truncated"] and media_root.exists() and root_is_safe:
        try:
            for index, entry in enumerate(media_root.iterdir()):
                if index >= MAX_MEDIA_ASSETS_TO_VERIFY:
                    result["verification_truncated"] = True
                    break
                if entry.name not in registered_keys:
                    result["unregistered_entries"] += 1
        except OSError:
            # Directory enumeration was incomplete; do not report a complete scan.
            result["invalid_entries"] += 1
            result["verification_truncated"] = True

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




DEFAULT_MEDIA_BACKUP_MAX_TOTAL_BYTES = 5 * 1024 * 1024 * 1024
MAX_MEDIA_BACKUP_TOTAL_BYTES = MAX_MEDIA_ASSETS_TO_VERIFY * MAX_MEDIA_ASSET_BYTES
MAX_MEDIA_BACKUP_MANIFEST_BYTES = 4 * 1024 * 1024


def _cleanup_created_paths(files: list[Path], directories: list[Path]) -> None:
    for path in reversed(files):
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
    for path in reversed(directories):
        try:
            path.rmdir()
        except OSError:
            pass


def _copy_media_file(
    source: Path,
    destination: Path,
    expected_size: int,
    expected_hash: str,
    created_files: list[Path],
) -> None:
    digest = hashlib.sha256()
    copied = 0
    with source.open("rb") as source_stream:
        with destination.open("xb") as destination_stream:
            created_files.append(destination)
            while True:
                chunk = source_stream.read(min(1024 * 1024, expected_size - copied + 1))
                if not chunk:
                    break
                copied += len(chunk)
                if copied > expected_size:
                    raise BackupError("Media file changed while it was being copied")
                digest.update(chunk)
                destination_stream.write(chunk)
            destination_stream.flush()
            os.fsync(destination_stream.fileno())
    if copied != expected_size or digest.hexdigest() != expected_hash:
        raise BackupError("Media file changed or failed checksum verification during copy")
    _private_permissions(destination)


def _read_media_registry(database_path: Path) -> list[tuple[str, int, str]]:
    try:
        with closing(
            sqlite3.connect(f"{database_path.as_uri()}?mode=ro", uri=True)
        ) as connection:
            rows = connection.execute(
                "SELECT storage_key, file_size, content_hash FROM content_assets ORDER BY storage_key"
            ).fetchall()
    except sqlite3.Error as exc:
        raise BackupError("Media asset registry could not be read") from exc
    if len(rows) > MAX_MEDIA_ASSETS_TO_VERIFY:
        raise BackupError("Media asset registry exceeds the configured verification limit")
    return [(str(key), int(size), str(digest)) for key, size, digest in rows]


def backup_media_assets(
    database: str | Path,
    destination: str | Path,
    *,
    max_total_bytes: int = DEFAULT_MEDIA_BACKUP_MAX_TOTAL_BYTES,
) -> dict[str, Any]:
    """Copy verified registered media into a new private directory with a checksum manifest."""
    if (
        isinstance(max_total_bytes, bool)
        or not isinstance(max_total_bytes, int)
        or not 1 <= max_total_bytes <= MAX_MEDIA_BACKUP_TOTAL_BYTES
    ):
        raise BackupError("Media backup size limit is outside the supported range")
    database_path = Path(database).expanduser().resolve(strict=True)
    if not database_path.is_file():
        raise BackupError("Media backup source must be a regular database file")
    source_root = database_path.parent / "content_assets"
    source_verification = verify_media_assets(database_path)
    if source_verification.get("ok") is not True:
        raise BackupError("Media source failed integrity verification")
    rows = _read_media_registry(database_path)
    total_bytes = sum(size for _, size, _ in rows)
    if total_bytes > max_total_bytes:
        raise BackupError("Registered media exceeds the requested backup size limit")

    destination_path = Path(destination).expanduser().absolute()
    source_root_resolved = source_root.resolve(strict=False)
    destination_resolved = destination_path.resolve(strict=False)
    if (
        destination_resolved == source_root_resolved
        or destination_resolved.is_relative_to(source_root_resolved)
    ):
        raise BackupError("Media backup destination must be outside the source media directory")
    destination_path.parent.mkdir(parents=True, exist_ok=True)

    created_files: list[Path] = []
    created_directories: list[Path] = []
    try:
        destination_path.mkdir(mode=0o700, exist_ok=False)
        created_directories.append(destination_path)
        media_destination = destination_path / "content_assets"
        media_destination.mkdir(mode=0o700)
        created_directories.append(media_destination)

        resolved_root = source_root.resolve(strict=False)
        assets: list[dict[str, Any]] = []
        for storage_key, expected_size, expected_hash in rows:
            if (
                not _MEDIA_STORAGE_KEY_PATTERN.fullmatch(storage_key)
                or not 0 <= expected_size <= MAX_MEDIA_ASSET_BYTES
                or not re.fullmatch(r"[0-9a-f]{64}", expected_hash)
            ):
                raise BackupError("Media registry contains an invalid asset entry")
            source_candidate = source_root / storage_key
            if source_candidate.is_symlink():
                raise BackupError("Media source contains a symbolic link")
            try:
                source_file = source_candidate.resolve(strict=True)
            except OSError as exc:
                raise BackupError("A registered media file is missing or inaccessible") from exc
            if source_file.parent != resolved_root or not source_file.is_file():
                raise BackupError("A registered media file is outside the media directory")
            target = media_destination / storage_key
            _copy_media_file(
                source_file,
                target,
                expected_size,
                expected_hash,
                created_files,
            )
            assets.append(
                {
                    "storage_key": storage_key,
                    "byte_size": expected_size,
                    "sha256": expected_hash,
                }
            )

        manifest = {
            "format_version": 1,
            "created_at": datetime.now(UTC).isoformat(),
            "source_database_name": database_path.name,
            "asset_count": len(assets),
            "total_bytes": total_bytes,
            "assets": assets,
        }
        manifest_path = destination_path / "manifest.json"
        with manifest_path.open("x", encoding="utf-8") as stream:
            created_files.append(manifest_path)
            json.dump(manifest, stream, ensure_ascii=False, sort_keys=True, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        _private_permissions(manifest_path)
        return {
            "ok": True,
            "destination_name": destination_path.name,
            "asset_count": len(assets),
            "total_bytes": total_bytes,
            "manifest": "manifest.json",
        }
    except Exception as exc:
        _cleanup_created_paths(created_files, created_directories)
        if isinstance(exc, BackupError):
            raise
        if isinstance(exc, OSError):
            raise BackupError("Media backup failed; existing files were not overwritten") from exc
        raise


def _read_media_backup_manifest(backup: str | Path) -> tuple[Path, dict[str, Any]]:
    input_path = Path(backup).expanduser()
    if input_path.is_symlink():
        raise BackupError("Media backup directory must not be a symbolic link")
    try:
        backup_path = input_path.resolve(strict=True)
    except OSError as exc:
        raise BackupError("Media backup directory is missing or inaccessible") from exc
    if not backup_path.is_dir():
        raise BackupError("Media backup source must be a directory")
    manifest_path = backup_path / "manifest.json"
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise BackupError("Media backup manifest is missing or unsafe")
    if manifest_path.stat().st_size > MAX_MEDIA_BACKUP_MANIFEST_BYTES:
        raise BackupError("Media backup manifest exceeds the size limit")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise BackupError("Media backup manifest is invalid") from exc
    if (
        not isinstance(manifest, dict)
        or isinstance(manifest.get("format_version"), bool)
        or not isinstance(manifest.get("format_version"), int)
        or manifest.get("format_version") != 1
        or not isinstance(manifest.get("assets"), list)
        or len(manifest["assets"]) > MAX_MEDIA_ASSETS_TO_VERIFY
        or isinstance(manifest.get("asset_count"), bool)
        or not isinstance(manifest.get("asset_count"), int)
        or isinstance(manifest.get("total_bytes"), bool)
        or not isinstance(manifest.get("total_bytes"), int)
        or not 0 <= manifest["total_bytes"] <= MAX_MEDIA_BACKUP_TOTAL_BYTES
    ):
        raise BackupError("Media backup manifest schema is invalid")
    return backup_path, manifest


def verify_media_backup(backup: str | Path) -> dict[str, Any]:
    """Verify every file and manifest entry in a previously created media backup."""
    backup_path, manifest = _read_media_backup_manifest(backup)
    assets = manifest["assets"]
    result: dict[str, Any] = {
        "ok": False,
        "asset_count": len(assets),
        "verified_assets": 0,
        "missing_assets": 0,
        "size_mismatched_assets": 0,
        "hash_mismatched_assets": 0,
        "invalid_entries": 0,
        "unregistered_entries": 0,
        "verification_truncated": False,
        "total_bytes": 0,
    }
    if manifest["asset_count"] != len(assets):
        result["invalid_entries"] += 1

    media_root = backup_path / "content_assets"
    if media_root.is_symlink() or not media_root.is_dir():
        result["invalid_entries"] += 1
        result["missing_assets"] += len(assets)
        return result
    resolved_root = media_root.resolve(strict=True)
    registered: set[str] = set()
    expected_total = 0

    for asset in assets:
        if not isinstance(asset, dict):
            result["invalid_entries"] += 1
            continue
        storage_key = asset.get("storage_key")
        expected_size = asset.get("byte_size")
        expected_hash = asset.get("sha256")
        if (
            not isinstance(storage_key, str)
            or not _MEDIA_STORAGE_KEY_PATTERN.fullmatch(storage_key)
            or storage_key in registered
            or isinstance(expected_size, bool)
            or not isinstance(expected_size, int)
            or not 0 <= expected_size <= MAX_MEDIA_ASSET_BYTES
            or not isinstance(expected_hash, str)
            or not re.fullmatch(r"[0-9a-f]{64}", expected_hash)
        ):
            result["invalid_entries"] += 1
            continue
        registered.add(storage_key)
        expected_total += expected_size
        candidate = media_root / storage_key
        if candidate.is_symlink():
            result["invalid_entries"] += 1
            continue
        try:
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
        try:
            actual_size = resolved.stat().st_size
            if actual_size != expected_size:
                result["size_mismatched_assets"] += 1
                continue
            if _sha256(resolved) != expected_hash:
                result["hash_mismatched_assets"] += 1
                continue
        except OSError:
            result["invalid_entries"] += 1
            continue
        result["verified_assets"] += 1

    result["total_bytes"] = expected_total
    if manifest["total_bytes"] != expected_total:
        result["invalid_entries"] += 1
    try:
        for index, entry in enumerate(media_root.iterdir()):
            if index >= MAX_MEDIA_ASSETS_TO_VERIFY:
                result["verification_truncated"] = True
                break
            if entry.name not in registered:
                result["unregistered_entries"] += 1
    except OSError:
        result["invalid_entries"] += 1
        result["verification_truncated"] = True

    try:
        for index, entry in enumerate(backup_path.iterdir()):
            if index >= MAX_MEDIA_ASSETS_TO_VERIFY:
                result["verification_truncated"] = True
                break
            if entry.name not in {"manifest.json", "content_assets"}:
                result["unregistered_entries"] += 1
    except OSError:
        result["invalid_entries"] += 1
        result["verification_truncated"] = True

    result["ok"] = not result["verification_truncated"] and all(
        result[key] == 0
        for key in (
            "missing_assets",
            "size_mismatched_assets",
            "hash_mismatched_assets",
            "invalid_entries",
            "unregistered_entries",
        )
    ) and result["verified_assets"] == len(assets)
    return result


def restore_media_assets(
    backup: str | Path,
    destination: str | Path,
    *,
    max_total_bytes: int = DEFAULT_MEDIA_BACKUP_MAX_TOTAL_BYTES,
) -> dict[str, Any]:
    """Restore a verified media backup into a new directory without overwriting files."""
    if (
        isinstance(max_total_bytes, bool)
        or not isinstance(max_total_bytes, int)
        or not 1 <= max_total_bytes <= MAX_MEDIA_BACKUP_TOTAL_BYTES
    ):
        raise BackupError("Media restore size limit is outside the supported range")
    backup_path, manifest = _read_media_backup_manifest(backup)
    if manifest["total_bytes"] > max_total_bytes:
        raise BackupError("Media backup exceeds the requested restore size limit")
    verification = verify_media_backup(backup_path)
    if verification.get("ok") is not True:
        raise BackupError("Media backup failed integrity verification")
    destination_path = Path(destination).expanduser().absolute()
    destination_resolved = destination_path.resolve(strict=False)
    if (
        destination_resolved == backup_path
        or destination_resolved.is_relative_to(backup_path)
    ):
        raise BackupError("Media restore destination must be outside the backup directory")
    destination_path.parent.mkdir(parents=True, exist_ok=True)

    created_files: list[Path] = []
    created_directories: list[Path] = []
    try:
        destination_path.mkdir(mode=0o700, exist_ok=False)
        created_directories.append(destination_path)
        source_root = backup_path / "content_assets"
        resolved_root = source_root.resolve(strict=True)
        for asset in manifest["assets"]:
            storage_key = asset["storage_key"]
            source = source_root / storage_key
            if source.is_symlink():
                raise BackupError("Media backup contains a symbolic link")
            resolved_source = source.resolve(strict=True)
            if resolved_source.parent != resolved_root or not resolved_source.is_file():
                raise BackupError("Media backup file is outside its asset directory")
            target = destination_path / storage_key
            _copy_media_file(
                resolved_source,
                target,
                asset["byte_size"],
                asset["sha256"],
                created_files,
            )
        return {
            "restored": True,
            "destination_name": destination_path.name,
            "asset_count": verification["asset_count"],
            "total_bytes": verification["total_bytes"],
            "destination_overwritten": False,
        }
    except Exception as exc:
        _cleanup_created_paths(created_files, created_directories)
        if isinstance(exc, BackupError):
            raise
        if isinstance(exc, OSError):
            raise BackupError("Media restore failed; existing files were not overwritten") from exc
        raise


def verify_backup(backup: str | Path) -> dict[str, Any]:
    """Verify a backup manifest, checksum, size, and SQLite integrity without writing files."""
    backup_path = Path(backup).expanduser().resolve(strict=True)
    if not backup_path.is_file():
        raise BackupError("Backup source must be a regular file")
    manifest_path = backup_path.with_suffix(backup_path.suffix + ".manifest.json")
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
    return {
        "verified": True,
        "backup_name": backup_path.name,
        "byte_size": backup_path.stat().st_size,
        "sha256": manifest["sha256"],
        "sqlite_integrity": "ok",
        "format_version": 1,
    }


def restore_database(backup: str | Path, destination: str | Path) -> dict[str, Any]:
    """Verify the backup manifest and SQLite integrity before atomically restoring a new file."""
    backup_path = Path(backup).expanduser().resolve(strict=True)
    destination_path = Path(destination).expanduser().absolute()
    if not backup_path.is_file():
        raise BackupError("Restore source must be a regular file")
    if backup_path == destination_path:
        raise BackupError("Restore destination must differ from backup")
    if destination_path.exists():
        raise BackupError("Restore destination already exists")
    verify_backup(backup_path)
    destination_path.parent.mkdir(parents=True, exist_ok=True)

    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix=".mrhub-restore-", suffix=".sqlite3", dir=destination_path.parent, delete=False
        ) as temporary:
            temporary_path = Path(temporary.name)
        with (
            closing(sqlite3.connect(backup_path)) as backup_connection,
            closing(sqlite3.connect(temporary_path)) as destination_connection,
        ):
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


def main(argv: list[str] | None = None) -> int:
    """Run explicit, no-overwrite database recovery operations from the command line."""
    parser = argparse.ArgumentParser(
        prog="mrhub-db",
        description="Create, verify, and restore local Hub database recovery files.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    backup_parser = commands.add_parser("backup", help="create a verified SQLite backup and manifest")
    backup_parser.add_argument("source", type=Path, help="source SQLite database")
    backup_parser.add_argument("destination", type=Path, help="new backup path; must not exist")

    restore_parser = commands.add_parser("restore", help="restore a verified backup to a new path")
    restore_parser.add_argument("backup", type=Path, help="backup database with its manifest")
    restore_parser.add_argument("destination", type=Path, help="new destination path; must not exist")

    verify_parser = commands.add_parser("verify-backup", help="verify a backup without restoring it")
    verify_parser.add_argument("backup", type=Path, help="backup database with its manifest")

    media_parser = commands.add_parser(
        "verify-media",
        help="read-only check of registered media files against database size and SHA-256 metadata",
    )
    media_parser.add_argument("database", type=Path, help="application SQLite database")

    backup_media_parser = commands.add_parser(
        "backup-media",
        help="copy verified registered media into a new private recovery directory",
    )
    backup_media_parser.add_argument("database", type=Path, help="application SQLite database")
    backup_media_parser.add_argument("destination", type=Path, help="new media backup directory")
    backup_media_parser.add_argument(
        "--max-total-bytes",
        type=int,
        default=DEFAULT_MEDIA_BACKUP_MAX_TOTAL_BYTES,
        help="maximum total media bytes to copy (default: 5 GiB)",
    )

    verify_media_backup_parser = commands.add_parser(
        "verify-media-backup",
        help="verify a media recovery directory without writing files",
    )
    verify_media_backup_parser.add_argument("backup", type=Path, help="media backup directory")

    restore_media_parser = commands.add_parser(
        "restore-media",
        help="restore verified media into a new directory without overwriting files",
    )
    restore_media_parser.add_argument("backup", type=Path, help="media backup directory")
    restore_media_parser.add_argument("destination", type=Path, help="new media directory")
    restore_media_parser.add_argument(
        "--max-total-bytes",
        type=int,
        default=DEFAULT_MEDIA_BACKUP_MAX_TOTAL_BYTES,
        help="maximum total media bytes to restore (default: 5 GiB)",
    )

    args = parser.parse_args(argv)
    try:
        if args.command == "backup":
            result = backup_database(args.source, args.destination)
        elif args.command == "restore":
            result = restore_database(args.backup, args.destination)
        elif args.command == "verify-backup":
            result = verify_backup(args.backup)
        elif args.command == "verify-media":
            result = verify_media_assets(args.database)
        elif args.command == "backup-media":
            result = backup_media_assets(
                args.database,
                args.destination,
                max_total_bytes=args.max_total_bytes,
            )
        elif args.command == "verify-media-backup":
            result = verify_media_backup(args.backup)
        else:
            result = restore_media_assets(
                args.backup,
                args.destination,
                max_total_bytes=args.max_total_bytes,
            )
    except (BackupError, OSError) as exc:
        print(
            json.dumps(
                {"ok": False, "error": str(exc)},
                ensure_ascii=False,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2

    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    if args.command in {"verify-media", "verify-media-backup"} and result.get("ok") is not True:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
