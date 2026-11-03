"""Private media asset metadata and file storage with generated path keys."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from mrhub.infrastructure.database import TaskRepository

MAX_UPLOAD_BYTES = 25_000_000
MAX_OUTPUT_BYTES = 100_000_000
_EXTENSIONS = {
    "video/mp4": ".mp4",
    "video/quicktime": ".mov",
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "audio/mpeg": ".mp3",
    "audio/wav": ".wav",
}
_STORAGE_KEY_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\.(?:mp4|mov|jpg|png|webp|mp3|wav)$"
)


class MediaAssetBusy(RuntimeError):
    """Raised when an asset is currently being modified by a media operation."""


class MediaAssetOwnershipConflict(RuntimeError):
    """Raised when deleting an asset could cascade into another owner's media."""


class MediaAssetRepository:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self.tasks = TaskRepository(database_path)
        self.tasks.initialize()
        self.storage_root = database_path.parent / "content_assets"
        self.storage_root.mkdir(parents=True, exist_ok=True, mode=0o700)

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()

    @staticmethod
    def _digest(content: bytes | bytearray) -> str:
        return hashlib.sha256(content).hexdigest()

    @staticmethod
    def _record(row) -> dict[str, object]:
        return {
            "asset_id": row["asset_id"],
            "owner_user_id": row["owner_user_id"],
            "source_asset_id": row["source_asset_id"],
            "original_filename": row["original_filename"],
            "media_type": row["media_type"],
            "storage_key": row["storage_key"],
            "file_size": row["file_size"],
            "content_hash": row["content_hash"],
            "processing_status": row["processing_status"],
            "processing_profile": row["processing_profile"],
            "error_code": row["error_code"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def file_path(self, storage_key: str) -> Path:
        if not _STORAGE_KEY_PATTERN.fullmatch(storage_key):
            raise ValueError("Invalid internal media storage key")
        root = self.storage_root.resolve()
        path = (root / storage_key).resolve()
        if path.parent != root:
            raise ValueError("Media path escapes storage root")
        return path

    def new_output_target(self) -> tuple[str, str, Path]:
        asset_id = str(uuid4())
        key = f"{asset_id}.mp4"
        return asset_id, key, self.file_path(key)

    def store_upload(
        self, owner_user_id: str, filename: str, media_type: str, content: bytes | bytearray
    ) -> dict[str, object]:
        if media_type not in _EXTENSIONS:
            raise ValueError("Unsupported media type")
        if not content or len(content) > MAX_UPLOAD_BYTES:
            raise ValueError("Media upload size is outside the allowed range")
        asset_id = str(uuid4())
        storage_key = f"{asset_id}{_EXTENSIONS[media_type]}"
        path = self.file_path(storage_key)
        now = self._now()
        try:
            with path.open("xb") as file:
                file.write(content)
                file.flush()
            with self.tasks._connection() as connection:
                connection.execute(
                    """
                    INSERT INTO content_assets (
                        asset_id, owner_user_id, source_asset_id, original_filename,
                        media_type, storage_key, file_size, content_hash,
                        processing_status, processing_profile, error_code, created_at, updated_at
                    ) VALUES (?, ?, NULL, ?, ?, ?, ?, ?, 'stored', NULL, NULL, ?, ?)
                    """,
                    (
                        asset_id,
                        owner_user_id,
                        filename,
                        media_type,
                        storage_key,
                        len(content),
                        self._digest(content),
                        now,
                        now,
                    ),
                )
                row = connection.execute(
                    "SELECT * FROM content_assets WHERE asset_id = ? AND owner_user_id = ?",
                    (asset_id, owner_user_id),
                ).fetchone()
        except Exception:
            path.unlink(missing_ok=True)
            raise
        assert row is not None
        return self._record(row)

    def get(self, owner_user_id: str, asset_id: UUID) -> dict[str, object] | None:
        with self.tasks._connection() as connection:
            row = connection.execute(
                "SELECT * FROM content_assets WHERE asset_id = ? AND owner_user_id = ?",
                (str(asset_id), owner_user_id),
            ).fetchone()
        return self._record(row) if row is not None else None

    def list_assets(self, owner_user_id: str, limit: int = 50) -> list[dict[str, object]]:
        bounded_limit = max(1, min(limit, 100))
        with self.tasks._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM content_assets WHERE owner_user_id = ? "
                "ORDER BY created_at DESC LIMIT ?",
                (owner_user_id, bounded_limit),
            ).fetchall()
        return [self._record(row) for row in rows]

    def begin_processing(self, owner_user_id: str, asset_id: UUID) -> dict[str, object] | None:
        now = self._now()
        with self.tasks._connection() as connection:
            cursor = connection.execute(
                """
                UPDATE content_assets
                SET processing_status = 'processing', processing_profile = 'video_mp4_720p',
                    error_code = NULL, updated_at = ?
                WHERE asset_id = ? AND owner_user_id = ?
                  AND source_asset_id IS NULL
                  AND media_type IN ('video/mp4', 'video/quicktime')
                  AND processing_status IN ('stored', 'failed')
                  AND NOT EXISTS (
                      SELECT 1 FROM content_assets child
                      WHERE child.source_asset_id = content_assets.asset_id
                  )
                """,
                (now, str(asset_id), owner_user_id),
            )
            if cursor.rowcount != 1:
                return None
            row = connection.execute(
                "SELECT * FROM content_assets WHERE asset_id = ? AND owner_user_id = ?",
                (str(asset_id), owner_user_id),
            ).fetchone()
        return self._record(row) if row is not None else None

    def fail_processing(
        self, owner_user_id: str, asset_id: UUID, error_code: str
    ) -> None:
        with self.tasks._connection() as connection:
            connection.execute(
                """
                UPDATE content_assets SET processing_status = 'failed',
                    error_code = ?, updated_at = ?
                WHERE asset_id = ? AND owner_user_id = ? AND processing_status = 'processing'
                """,
                (error_code[:80], self._now(), str(asset_id), owner_user_id),
            )

    def register_transcoded_output(
        self,
        owner_user_id: str,
        source_asset_id: UUID,
        output_asset_id: str,
        storage_key: str,
        output_path: Path,
        output_filename: str,
    ) -> dict[str, object]:
        size = output_path.stat().st_size
        if size <= 0 or size > MAX_OUTPUT_BYTES:
            raise ValueError("Transcoded output size is outside the allowed range")
        digest = hashlib.sha256()
        with output_path.open("rb") as file:
            for chunk in iter(lambda: file.read(1024 * 1024), b""):
                digest.update(chunk)
        now = self._now()
        with self.tasks._connection() as connection:
            source = connection.execute(
                "SELECT 1 FROM content_assets WHERE asset_id = ? AND owner_user_id = ? "
                "AND processing_status = 'processing' AND source_asset_id IS NULL",
                (str(source_asset_id), owner_user_id),
            ).fetchone()
            if source is None:
                raise ValueError("Media source is no longer in a processing state")
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
                    output_asset_id,
                    owner_user_id,
                    str(source_asset_id),
                    output_filename,
                    storage_key,
                    size,
                    digest.hexdigest(),
                    now,
                    now,
                ),
            )
            connection.execute(
                "UPDATE content_assets SET processing_status = 'processed', "
                "processing_profile = 'video_mp4_720p', error_code = NULL, updated_at = ? "
                "WHERE asset_id = ? AND owner_user_id = ?",
                (now, str(source_asset_id), owner_user_id),
            )
            row = connection.execute(
                "SELECT * FROM content_assets WHERE asset_id = ? AND owner_user_id = ?",
                (output_asset_id, owner_user_id),
            ).fetchone()
        assert row is not None
        return self._record(row)

    def register_rendered_output(
        self,
        owner_user_id: str,
        output_asset_id: str,
        storage_key: str,
        output_path: Path,
        output_filename: str,
        *,
        task_id: UUID,
        render_id: UUID,
        lease,
        task_result: dict[str, object],
    ) -> dict[str, object]:
        """Atomically register a generated render only while its worker lease is current."""
        try:
            asset_uuid = UUID(output_asset_id)
            expected_path = self.file_path(storage_key)
        except (ValueError, TypeError) as exc:
            raise ValueError("Invalid rendered output identity") from exc
        if storage_key != f"{asset_uuid}.mp4" or output_path.resolve() != expected_path:
            raise ValueError("Rendered output path does not match its generated asset key")
        size = output_path.stat().st_size
        if size <= 0 or size > MAX_OUTPUT_BYTES:
            raise ValueError("Rendered output size is outside the allowed range")
        digest = hashlib.sha256()
        with output_path.open("rb") as file:
            for chunk in iter(lambda: file.read(1024 * 1024), b""):
                digest.update(chunk)
        now = self._now()
        with self.tasks._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            current = connection.execute(
                """SELECT 1 FROM worker_executions AS e
                   JOIN tasks AS t ON t.task_id = e.task_id
                   WHERE e.task_id = ? AND e.lease_owner = ? AND e.execution_token = ?
                     AND e.lease_expires_at > ? AND t.status = 'running'""",
                (str(task_id), lease.owner, lease.fencing_token, now),
            ).fetchone()
            if current is None:
                raise ValueError("Render worker lease is no longer current")
            connection.execute(
                """INSERT INTO content_assets (
                    asset_id, owner_user_id, source_asset_id, original_filename,
                    media_type, storage_key, file_size, content_hash,
                    processing_status, processing_profile, error_code, created_at, updated_at
                ) VALUES (?, ?, NULL, ?, 'video/mp4', ?, ?, ?, 'processed',
                          'video_render_cut_v1', NULL, ?, ?)""",
                (
                    str(asset_uuid), owner_user_id, output_filename, storage_key,
                    size, digest.hexdigest(), now, now,
                ),
            )
            completed = connection.execute(
                """UPDATE video_render_runs
                   SET status = 'completed', output_asset_id = ?, error_code = NULL, updated_at = ?
                   WHERE render_id = ? AND task_id = ? AND owner_user_id = ? AND status = 'running'
                     AND EXISTS (
                       SELECT 1 FROM worker_executions AS e
                       WHERE e.task_id = ? AND e.lease_owner = ? AND e.execution_token = ?
                         AND e.lease_expires_at > ?
                     )""",
                (
                    str(asset_uuid), now, str(render_id), str(task_id), owner_user_id,
                    str(task_id), lease.owner, lease.fencing_token, now,
                ),
            )
            if completed.rowcount != 1:
                raise ValueError("Render job is no longer owned by this worker lease")
            task_updated = connection.execute(
                """UPDATE tasks SET status = 'succeeded', updated_at = ?
                   WHERE task_id = ? AND status = 'running'
                     AND EXISTS (
                       SELECT 1 FROM worker_executions AS e
                       WHERE e.task_id = tasks.task_id AND e.lease_owner = ?
                         AND e.execution_token = ? AND e.lease_expires_at > ?
                     )""",
                (now, str(task_id), lease.owner, lease.fencing_token, now),
            )
            if task_updated.rowcount != 1:
                raise ValueError("Render task was cancelled or its lease expired")
            execution_updated = connection.execute(
                """UPDATE worker_executions
                   SET result_json = ?, error_code = NULL, finished_at = ?,
                       next_attempt_at = NULL
                   WHERE task_id = ? AND lease_owner = ? AND execution_token = ?
                     AND lease_expires_at > ?""",
                (
                    json.dumps(task_result, ensure_ascii=False, sort_keys=True),
                    now, str(task_id), lease.owner, lease.fencing_token, now,
                ),
            )
            if execution_updated.rowcount != 1:
                raise ValueError("Render worker lease is no longer current")
            connection.execute(
                """UPDATE idempotency_records SET status = 'completed'
                   WHERE task_id = ? AND scope = ?""",
                (str(task_id), f"video-render:{owner_user_id}"),
            )
            row = connection.execute(
                "SELECT * FROM content_assets WHERE asset_id = ? AND owner_user_id = ?",
                (str(asset_uuid), owner_user_id),
            ).fetchone()
        if row is None:
            raise RuntimeError("Rendered media asset registration failed")
        return self._record(row)

    def delete(self, owner_user_id: str, asset_id: UUID) -> list[str] | None:
        now = self._now()
        with self.tasks._connection() as connection:
            # Serialize the state check with begin_processing before deciding to delete.
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT source_asset_id, processing_status FROM content_assets "
                "WHERE asset_id = ? AND owner_user_id = ?",
                (str(asset_id), owner_user_id),
            ).fetchone()
            if row is None:
                return None
            if row["processing_status"] == "processing":
                raise MediaAssetBusy("Media asset is currently being processed")
            if row["source_asset_id"] is None:
                foreign_child = connection.execute(
                    "SELECT 1 FROM content_assets "
                    "WHERE source_asset_id = ? AND owner_user_id <> ? LIMIT 1",
                    (str(asset_id), owner_user_id),
                ).fetchone()
                if foreign_child is not None:
                    raise MediaAssetOwnershipConflict(
                        "Media asset has a derivative owned by another user"
                    )
            if row["source_asset_id"] is not None:
                rows = connection.execute(
                    "SELECT storage_key FROM content_assets WHERE asset_id = ? AND owner_user_id = ?",
                    (str(asset_id), owner_user_id),
                ).fetchall()
                keys = [item["storage_key"] for item in rows]
                connection.execute(
                    "DELETE FROM content_assets WHERE asset_id = ? AND owner_user_id = ?",
                    (str(asset_id), owner_user_id),
                )
                connection.execute(
                    "UPDATE content_assets SET processing_status = 'stored', "
                    "processing_profile = NULL, error_code = NULL, updated_at = ? "
                    "WHERE asset_id = ? AND owner_user_id = ?",
                    (now, row["source_asset_id"], owner_user_id),
                )
            else:
                rows = connection.execute(
                    "SELECT storage_key FROM content_assets "
                    "WHERE owner_user_id = ? AND (asset_id = ? OR source_asset_id = ?)",
                    (owner_user_id, str(asset_id), str(asset_id)),
                ).fetchall()
                keys = [item["storage_key"] for item in rows]
                # Persist cleanup intent in the same transaction as metadata deletion.
                # A process crash after COMMIT can therefore never lose the file key.
                connection.executemany(
                    "INSERT OR IGNORE INTO media_file_cleanup "
                    "(cleanup_id, owner_user_id, storage_key, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    [
                        (str(uuid4()), owner_user_id, key, now, now)
                        for key in keys
                    ],
                )
                connection.execute(
                    "DELETE FROM content_assets WHERE asset_id = ? AND owner_user_id = ?",
                    (str(asset_id), owner_user_id),
                )
                return keys

            connection.executemany(
                "INSERT OR IGNORE INTO media_file_cleanup "
                "(cleanup_id, owner_user_id, storage_key, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?)",
                [
                    (str(uuid4()), owner_user_id, key, now, now)
                    for key in keys
                ],
            )
        return keys

    def cleanup_pending_files(self, owner_user_id: str, limit: int = 100) -> int:
        """Retry bounded, owner-scoped file cleanup; return the number still pending."""
        bounded_limit = max(1, min(limit, 100))
        with self.tasks._connection() as connection:
            rows = connection.execute(
                "SELECT cleanup_id, storage_key FROM media_file_cleanup "
                "WHERE owner_user_id = ? "
                "ORDER BY attempt_count, updated_at, created_at LIMIT ?",
                (owner_user_id, bounded_limit),
            ).fetchall()

        for row in rows:
            try:
                self.file_path(str(row["storage_key"])).unlink(missing_ok=True)
            except (OSError, ValueError):
                # Failed entries move behind unattempted entries so a persistently
                # unavailable file cannot starve the rest of this owner's queue.
                with self.tasks._connection() as connection:
                    connection.execute(
                        "UPDATE media_file_cleanup "
                        "SET attempt_count = attempt_count + 1, updated_at = ? "
                        "WHERE cleanup_id = ? AND owner_user_id = ?",
                        (self._now(), row["cleanup_id"], owner_user_id),
                    )
                continue
            with self.tasks._connection() as connection:
                connection.execute(
                    "DELETE FROM media_file_cleanup WHERE cleanup_id = ? AND owner_user_id = ?",
                    (row["cleanup_id"], owner_user_id),
                )

        with self.tasks._connection() as connection:
            pending = connection.execute(
                "SELECT COUNT(*) AS total FROM media_file_cleanup WHERE owner_user_id = ?",
                (owner_user_id,),
            ).fetchone()
        return int(pending["total"]) if pending is not None else 0
