"""Owner-scoped content draft storage with deduplication and revision history."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from mrhub.infrastructure.database import TaskRepository
from mrhub.media.repository import MAX_UPLOAD_BYTES, MediaAssetRepository


class MediaAttachmentError(ValueError):
    """Raised when a media asset cannot safely be attached to a draft."""


class ContentDraftRepository:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self.tasks = TaskRepository(database_path)
        self.tasks.initialize()

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()

    @staticmethod
    def _hash(
        platform: str,
        content_type: str,
        body: str,
        hashtags: list[str],
        media_asset_id: str | None = None,
    ) -> str:
        payload: dict[str, object] = {
            "platform": platform,
            "content_type": content_type,
            "body": " ".join(body.split()),
            "hashtags": sorted(tag.strip().casefold() for tag in hashtags),
        }
        # Preserve historical hashes for text-only drafts; bind media only when present.
        if media_asset_id is not None:
            payload["media_asset_id"] = str(media_asset_id)
        canonical = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()

    @staticmethod
    def _record(row) -> dict[str, object]:
        return {
            "draft_id": row["draft_id"],
            "owner_user_id": row["owner_user_id"],
            "platform": row["platform"],
            "content_type": row["content_type"],
            "title": row["title"],
            "body": row["body"],
            "hashtags": json.loads(row["hashtags_json"]),
            "media_asset_id": row["media_asset_id"],
            "status": row["status"],
            "content_hash": row["content_hash"],
            "version": row["version"],
            "approved_by": row["approved_by"],
            "approved_at": row["approved_at"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def _validate_media_asset(
        self,
        owner_user_id: str,
        platform: str,
        media_asset_id: str | UUID | None,
    ) -> str | None:
        if media_asset_id is None:
            return None
        try:
            asset_uuid = UUID(str(media_asset_id))
        except (TypeError, ValueError) as exc:
            raise MediaAttachmentError("Invalid media asset ID") from exc
        if platform not in {"telegram", "instagram"}:
            raise MediaAttachmentError("Media attachments are not supported for this platform")
        asset = MediaAssetRepository(self.database_path).get(owner_user_id, asset_uuid)
        if asset is None:
            raise MediaAttachmentError("Media asset is missing or belongs to another owner")
        allowed_types = (
            {"image/jpeg", "image/png"}
            if platform == "instagram"
            else {"image/jpeg", "image/png", "video/mp4"}
        )
        if asset["media_type"] not in allowed_types:
            supported = "JPEG and PNG" if platform == "instagram" else "JPEG, PNG, and MP4"
            raise MediaAttachmentError(
                f"{platform.title()} media attachments support {supported} only"
            )
        if int(asset["file_size"]) < 1 or int(asset["file_size"]) > MAX_UPLOAD_BYTES:
            raise MediaAttachmentError("Media asset size is outside the publishing limit")
        return str(asset["asset_id"])

    @staticmethod
    def _save_version(
        connection, record: dict[str, object], changed_by: str, created_at: str
    ) -> None:
        connection.execute(
            """
            INSERT INTO content_draft_versions (
                version_id, draft_id, owner_user_id, version_number, platform,
                content_type, title, body, hashtags_json, content_hash, media_asset_id,
                changed_by, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid4()),
                record["draft_id"],
                record["owner_user_id"],
                record["version"],
                record["platform"],
                record["content_type"],
                record["title"],
                record["body"],
                json.dumps(record["hashtags"], ensure_ascii=False, separators=(",", ":")),
                record["content_hash"],
                record["media_asset_id"],
                changed_by,
                created_at,
            ),
        )

    def find_duplicate(self, owner_user_id: str, content_hash: str) -> dict[str, object] | None:
        with self.tasks._connection() as connection:
            row = connection.execute(
                "SELECT * FROM content_drafts WHERE owner_user_id = ? AND content_hash = ?",
                (owner_user_id, content_hash),
            ).fetchone()
        return self._record(row) if row is not None else None

    def create(
        self,
        owner_user_id: str,
        changed_by: str,
        *,
        platform: str,
        content_type: str,
        title: str,
        body: str,
        hashtags: list[str],
        media_asset_id: str | UUID | None = None,
    ) -> dict[str, object]:
        title = title.strip()
        body = body.strip()
        hashtags = [tag.strip() for tag in hashtags]
        media_asset_id = self._validate_media_asset(owner_user_id, platform, media_asset_id)
        content_hash = self._hash(platform, content_type, body, hashtags, media_asset_id)
        draft_id = str(uuid4())
        now = self._now()
        record = {
            "draft_id": draft_id,
            "owner_user_id": owner_user_id,
            "platform": platform,
            "content_type": content_type,
            "title": title,
            "body": body,
            "hashtags": hashtags,
            "media_asset_id": media_asset_id,
            "status": "draft",
            "content_hash": content_hash,
            "version": 1,
            "approved_by": None,
            "approved_at": None,
            "created_at": now,
            "updated_at": now,
        }
        with self.tasks._connection() as connection:
            connection.execute(
                """
                INSERT INTO content_drafts (
                    draft_id, owner_user_id, platform, content_type, title, body,
                    hashtags_json, media_asset_id, status, content_hash, version, approved_by,
                    approved_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'draft', ?, 1, NULL, NULL, ?, ?)
                """,
                (
                    draft_id,
                    owner_user_id,
                    platform,
                    content_type,
                    title,
                    body,
                    json.dumps(hashtags, ensure_ascii=False, separators=(",", ":")),
                    media_asset_id,
                    content_hash,
                    now,
                    now,
                ),
            )
            self._save_version(connection, record, changed_by, now)
            row = connection.execute(
                "SELECT * FROM content_drafts WHERE draft_id = ? AND owner_user_id = ?",
                (draft_id, owner_user_id),
            ).fetchone()
        assert row is not None
        return self._record(row)

    def get(self, owner_user_id: str, draft_id: UUID) -> dict[str, object] | None:
        with self.tasks._connection() as connection:
            row = connection.execute(
                "SELECT * FROM content_drafts WHERE draft_id = ? AND owner_user_id = ?",
                (str(draft_id), owner_user_id),
            ).fetchone()
        return self._record(row) if row is not None else None

    def list_drafts(
        self, owner_user_id: str, limit: int = 50, status: str | None = None
    ) -> list[dict[str, object]]:
        bounded_limit = max(1, min(limit, 100))
        query = "SELECT * FROM content_drafts WHERE owner_user_id = ?"
        params: tuple[object, ...] = (owner_user_id,)
        if status is not None:
            query += " AND status = ?"
            params += (status,)
        query += " ORDER BY updated_at DESC LIMIT ?"
        params += (bounded_limit,)
        with self.tasks._connection() as connection:
            rows = connection.execute(query, params).fetchall()
        return [self._record(row) for row in rows]

    def update(
        self, owner_user_id: str, changed_by: str, draft_id: UUID, changes: dict[str, object]
    ) -> dict[str, object] | None:
        allowed = {"platform", "content_type", "title", "body", "hashtags", "media_asset_id"}
        if not changes or any(key not in allowed for key in changes):
            raise ValueError("At least one supported field must be updated")
        with self.tasks._connection() as connection:
            row = connection.execute(
                "SELECT * FROM content_drafts WHERE draft_id = ? AND owner_user_id = ?",
                (str(draft_id), owner_user_id),
            ).fetchone()
            if row is None:
                return None
            if row["status"] == "archived":
                raise ValueError("Archived draft must be restored before editing")
            current = self._record(row)
            current.update(changes)
            current["title"] = str(current["title"]).strip()
            current["body"] = str(current["body"]).strip()
            current["hashtags"] = [str(tag).strip() for tag in current["hashtags"]]
            current["media_asset_id"] = self._validate_media_asset(
                owner_user_id,
                str(current["platform"]),
                current.get("media_asset_id"),
            )
            current["content_hash"] = self._hash(
                str(current["platform"]),
                str(current["content_type"]),
                str(current["body"]),
                list(current["hashtags"]),
                current["media_asset_id"],
            )
            current["version"] = int(row["version"]) + 1
            current["status"] = "draft"
            current["approved_by"] = None
            current["approved_at"] = None
            current["updated_at"] = self._now()
            connection.execute(
                """
                UPDATE content_drafts
                SET platform = ?, content_type = ?, title = ?, body = ?, hashtags_json = ?,
                    media_asset_id = ?, status = 'draft', content_hash = ?, version = ?, approved_by = NULL,
                    approved_at = NULL, updated_at = ?
                WHERE draft_id = ? AND owner_user_id = ?
                """,
                (
                    current["platform"],
                    current["content_type"],
                    current["title"],
                    current["body"],
                    json.dumps(current["hashtags"], ensure_ascii=False, separators=(",", ":")),
                    current["media_asset_id"],
                    current["content_hash"],
                    current["version"],
                    current["updated_at"],
                    str(draft_id),
                    owner_user_id,
                ),
            )
            self._save_version(connection, current, changed_by, str(current["updated_at"]))
            updated = connection.execute(
                "SELECT * FROM content_drafts WHERE draft_id = ? AND owner_user_id = ?",
                (str(draft_id), owner_user_id),
            ).fetchone()
        return self._record(updated) if updated is not None else None

    def approve(self, owner_user_id: str, draft_id: UUID) -> dict[str, object] | None:
        now = self._now()
        with self.tasks._connection() as connection:
            row = connection.execute(
                "SELECT status FROM content_drafts WHERE draft_id = ? AND owner_user_id = ?",
                (str(draft_id), owner_user_id),
            ).fetchone()
            if row is None:
                return None
            if row["status"] == "archived":
                raise ValueError("Archived draft cannot be approved")
            connection.execute(
                """
                UPDATE content_drafts SET status = 'approved', approved_by = ?,
                    approved_at = ?, updated_at = ?
                WHERE draft_id = ? AND owner_user_id = ?
                """,
                (owner_user_id, now, now, str(draft_id), owner_user_id),
            )
            updated = connection.execute(
                "SELECT * FROM content_drafts WHERE draft_id = ? AND owner_user_id = ?",
                (str(draft_id), owner_user_id),
            ).fetchone()
        return self._record(updated) if updated is not None else None

    def revoke_approval(self, owner_user_id: str, draft_id: UUID) -> dict[str, object] | None:
        now = self._now()
        with self.tasks._connection() as connection:
            row = connection.execute(
                "SELECT status FROM content_drafts WHERE draft_id = ? AND owner_user_id = ?",
                (str(draft_id), owner_user_id),
            ).fetchone()
            if row is None:
                return None
            if row["status"] != "approved":
                raise ValueError("Only an approved draft can have its approval revoked")
            connection.execute(
                """
                UPDATE content_drafts SET status = 'draft', approved_by = NULL,
                    approved_at = NULL, updated_at = ?
                WHERE draft_id = ? AND owner_user_id = ?
                """,
                (now, str(draft_id), owner_user_id),
            )
            updated = connection.execute(
                "SELECT * FROM content_drafts WHERE draft_id = ? AND owner_user_id = ?",
                (str(draft_id), owner_user_id),
            ).fetchone()
        return self._record(updated) if updated is not None else None

    def archive(self, owner_user_id: str, draft_id: UUID) -> dict[str, object] | None:
        now = self._now()
        with self.tasks._connection() as connection:
            row = connection.execute(
                "SELECT 1 FROM content_drafts WHERE draft_id = ? AND owner_user_id = ?",
                (str(draft_id), owner_user_id),
            ).fetchone()
            if row is None:
                return None
            connection.execute(
                """
                UPDATE content_drafts SET status = 'archived', approved_by = NULL,
                    approved_at = NULL, updated_at = ?
                WHERE draft_id = ? AND owner_user_id = ?
                """,
                (now, str(draft_id), owner_user_id),
            )
            updated = connection.execute(
                "SELECT * FROM content_drafts WHERE draft_id = ? AND owner_user_id = ?",
                (str(draft_id), owner_user_id),
            ).fetchone()
        return self._record(updated) if updated is not None else None

    def restore(self, owner_user_id: str, draft_id: UUID) -> dict[str, object] | None:
        now = self._now()
        with self.tasks._connection() as connection:
            row = connection.execute(
                "SELECT status FROM content_drafts WHERE draft_id = ? AND owner_user_id = ?",
                (str(draft_id), owner_user_id),
            ).fetchone()
            if row is None:
                return None
            if row["status"] != "archived":
                raise ValueError("Only an archived draft can be restored")
            connection.execute(
                """
                UPDATE content_drafts SET status = 'draft', approved_by = NULL,
                    approved_at = NULL, updated_at = ?
                WHERE draft_id = ? AND owner_user_id = ?
                """,
                (now, str(draft_id), owner_user_id),
            )
            updated = connection.execute(
                "SELECT * FROM content_drafts WHERE draft_id = ? AND owner_user_id = ?",
                (str(draft_id), owner_user_id),
            ).fetchone()
        return self._record(updated) if updated is not None else None

    def versions(self, owner_user_id: str, draft_id: UUID) -> list[dict[str, object]] | None:
        with self.tasks._connection() as connection:
            exists = connection.execute(
                "SELECT 1 FROM content_drafts WHERE draft_id = ? AND owner_user_id = ?",
                (str(draft_id), owner_user_id),
            ).fetchone()
            if exists is None:
                return None
            rows = connection.execute(
                """
                SELECT version_id, draft_id, owner_user_id, version_number, platform,
                       content_type, title, body, hashtags_json, content_hash, media_asset_id,
                       changed_by, created_at
                FROM content_draft_versions
                WHERE draft_id = ? AND owner_user_id = ?
                ORDER BY version_number DESC
                """,
                (str(draft_id), owner_user_id),
            ).fetchall()
        return [
            {
                "version_id": row["version_id"],
                "draft_id": row["draft_id"],
                "version_number": row["version_number"],
                "platform": row["platform"],
                "content_type": row["content_type"],
                "title": row["title"],
                "body": row["body"],
                "hashtags": json.loads(row["hashtags_json"]),
                "media_asset_id": row["media_asset_id"],
                "content_hash": row["content_hash"],
                "changed_by": row["changed_by"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def delete(self, owner_user_id: str, draft_id: UUID) -> bool:
        with self.tasks._connection() as connection:
            cursor = connection.execute(
                "DELETE FROM content_drafts WHERE draft_id = ? AND owner_user_id = ?",
                (str(draft_id), owner_user_id),
            )
        return cursor.rowcount == 1
