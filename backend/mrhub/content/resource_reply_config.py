"""Owner-scoped settings for comment-triggered educational resource replies."""
from __future__ import annotations

from datetime import datetime, UTC
from pathlib import Path

from mrhub.content.repository import ContentDraftRepository

DEFAULT_RESOURCE_REPLY_CONFIG: dict[str, object] = {
    "keyword": "راهنما",
    "resource_url": "",
    "resource_label": "محتوای آموزشی",
    "intro_text": "سلام! ✨",
    "include_follow": True,
    "follow_cta_text": "اگر این آموزش برات مفیده، خوشحال می‌شیم صفحه‌مون رو دنبال کنی. 💚",
    "include_share": True,
    "share_cta_text": "این پست رو هم برای دوستانت بفرست تا افراد بیشتری از آموزش رایگان استفاده کنن. 📢",
}


class ResourceReplyConfigRepository:
    """Persist customizable reply fields without enabling any external automation."""

    def __init__(self, database_path: Path) -> None:
        self.tasks = ContentDraftRepository(database_path).tasks

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()

    def get(self, owner_user_id: str) -> dict[str, object]:
        with self.tasks._connection() as connection:
            row = connection.execute(
                "SELECT * FROM resource_reply_configs WHERE owner_user_id = ?",
                (owner_user_id,),
            ).fetchone()
        if row is None:
            return {**DEFAULT_RESOURCE_REPLY_CONFIG, "updated_at": None}
        return {
            "keyword": row["keyword"],
            "resource_url": row["resource_url"],
            "resource_label": row["resource_label"],
            "intro_text": row["intro_text"],
            "include_follow": bool(row["include_follow"]),
            "follow_cta_text": row["follow_cta_text"],
            "include_share": bool(row["include_share"]),
            "share_cta_text": row["share_cta_text"],
            "updated_at": row["updated_at"],
        }

    def save(self, owner_user_id: str, config: dict[str, object]) -> dict[str, object]:
        now = self._now()
        values = (
            owner_user_id,
            str(config["keyword"]),
            str(config["resource_url"]),
            str(config["resource_label"]),
            str(config["intro_text"]),
            int(bool(config["include_follow"])),
            str(config["follow_cta_text"]),
            int(bool(config["include_share"])),
            str(config["share_cta_text"]),
            now,
        )
        with self.tasks._connection() as connection:
            connection.execute(
                """INSERT INTO resource_reply_configs (
                    owner_user_id, keyword, resource_url, resource_label, intro_text,
                    include_follow, follow_cta_text, include_share, share_cta_text, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(owner_user_id) DO UPDATE SET
                    keyword = excluded.keyword,
                    resource_url = excluded.resource_url,
                    resource_label = excluded.resource_label,
                    intro_text = excluded.intro_text,
                    include_follow = excluded.include_follow,
                    follow_cta_text = excluded.follow_cta_text,
                    include_share = excluded.include_share,
                    share_cta_text = excluded.share_cta_text,
                    updated_at = excluded.updated_at""",
                values,
            )
        return self.get(owner_user_id)
