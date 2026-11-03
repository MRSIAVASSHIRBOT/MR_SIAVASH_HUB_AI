"""Owner-scoped persistence for video production brand profiles."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from mrhub.infrastructure.database import TaskRepository
from mrhub.video_intelligence.schemas import BrandIdentity


class VideoBrandRepository:
    """Persist brand identities with strict owner scoping."""

    def __init__(self, database_path: Path) -> None:
        self.tasks = TaskRepository(database_path)
        self.tasks.initialize()

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()

    @staticmethod
    def _record(row: sqlite3.Row) -> dict[str, object]:
        return {
            "profile_id": row["profile_id"],
            "brand_name": row["brand_name"],
            "handle": row["handle"],
            "logo_asset_id": row["logo_asset_id"],
            "colors": json.loads(row["colors_json"]),
            "font_preferences": json.loads(row["font_preferences_json"]),
            "tone": row["tone"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def create(self, owner_user_id: str, brand: BrandIdentity) -> dict[str, object]:
        profile_id = str(uuid4())
        now = self._now()
        with self.tasks._connection() as connection:
            connection.execute(
                """
                INSERT INTO video_brand_profiles (
                    profile_id, owner_user_id, brand_name, handle, logo_asset_id,
                    colors_json, font_preferences_json, tone, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    profile_id,
                    owner_user_id,
                    brand.brand_name,
                    brand.handle,
                    brand.logo_asset_id,
                    json.dumps(brand.colors, ensure_ascii=False),
                    json.dumps(brand.font_preferences, ensure_ascii=False),
                    brand.tone,
                    now,
                    now,
                ),
            )
            row = connection.execute(
                "SELECT * FROM video_brand_profiles WHERE profile_id = ? AND owner_user_id = ?",
                (profile_id, owner_user_id),
            ).fetchone()
        if row is None:
            raise RuntimeError("Created brand profile could not be read back")
        return self._record(row)

    def get(self, owner_user_id: str, profile_id: UUID) -> dict[str, object] | None:
        with self.tasks._connection() as connection:
            row = connection.execute(
                "SELECT * FROM video_brand_profiles WHERE profile_id = ? AND owner_user_id = ?",
                (str(profile_id), owner_user_id),
            ).fetchone()
        return self._record(row) if row is not None else None

    def list(self, owner_user_id: str, limit: int = 50) -> list[dict[str, object]]:
        bounded_limit = max(1, min(limit, 100))
        with self.tasks._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM video_brand_profiles WHERE owner_user_id = ? "
                "ORDER BY updated_at DESC LIMIT ?",
                (owner_user_id, bounded_limit),
            ).fetchall()
        return [self._record(row) for row in rows]

    def update(
        self, owner_user_id: str, profile_id: UUID, brand: BrandIdentity
    ) -> dict[str, object] | None:
        now = self._now()
        with self.tasks._connection() as connection:
            cursor = connection.execute(
                """
                UPDATE video_brand_profiles
                SET brand_name = ?, handle = ?, logo_asset_id = ?, colors_json = ?,
                    font_preferences_json = ?, tone = ?, updated_at = ?
                WHERE profile_id = ? AND owner_user_id = ?
                """,
                (
                    brand.brand_name,
                    brand.handle,
                    brand.logo_asset_id,
                    json.dumps(brand.colors, ensure_ascii=False),
                    json.dumps(brand.font_preferences, ensure_ascii=False),
                    brand.tone,
                    now,
                    str(profile_id),
                    owner_user_id,
                ),
            )
            if cursor.rowcount != 1:
                return None
            row = connection.execute(
                "SELECT * FROM video_brand_profiles WHERE profile_id = ? AND owner_user_id = ?",
                (str(profile_id), owner_user_id),
            ).fetchone()
        return self._record(row) if row is not None else None

    def delete(self, owner_user_id: str, profile_id: UUID) -> bool:
        with self.tasks._connection() as connection:
            cursor = connection.execute(
                "DELETE FROM video_brand_profiles WHERE profile_id = ? AND owner_user_id = ?",
                (str(profile_id), owner_user_id),
            )
        return cursor.rowcount == 1
