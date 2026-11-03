"""Owner-scoped editable video timeline drafts with optimistic concurrency."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from mrhub.infrastructure.database import TaskRepository


class TimelineConflict(ValueError):
    """Raised when a timeline draft version is stale or already exists."""


class TimelineBeat(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    start_seconds: float = Field(ge=0, le=60)
    end_seconds: float = Field(gt=0, le=60)
    generation_instruction: str = Field(min_length=1, max_length=1200)
    transition_to_next: str = Field(default="clean cinematic cut", max_length=240)
    source_timestamp_seconds: float | None = Field(default=None, ge=0, le=86_400)
    confidence: float | None = Field(default=None, ge=0, le=1)

    @model_validator(mode="after")
    def validate_interval(self) -> "TimelineBeat":
        if self.end_seconds <= self.start_seconds:
            raise ValueError("Timeline beat end must be after its start")
        return self


class TimelineDraftUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    expected_version: int = Field(ge=1)
    duration_seconds: int = Field(ge=3, le=60)
    aspect_ratio: str = Field(pattern=r"^(9:16|16:9|1:1|4:5)$")
    beats: list[TimelineBeat] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def validate_timeline(self) -> "TimelineDraftUpdate":
        previous_end = 0.0
        for beat in self.beats:
            if beat.end_seconds > self.duration_seconds:
                raise ValueError("Timeline beat exceeds draft duration")
            if beat.start_seconds < previous_end:
                raise ValueError("Timeline beats must be ordered and cannot overlap")
            previous_end = beat.end_seconds
        return self


class VideoTimelineDraftRepository:
    """Persist bounded editable timelines with owner checks and version fencing."""

    MAX_TIMELINE_BYTES = 60_000

    def __init__(self, database_path: Path) -> None:
        self.tasks = TaskRepository(database_path)
        self.tasks.initialize()

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()

    @staticmethod
    def _record(row: sqlite3.Row) -> dict[str, object]:
        return {
            "draft_id": row["draft_id"],
            "analysis_id": row["analysis_id"],
            "asset_id": row["asset_id"],
            "duration_seconds": row["duration_seconds"],
            "aspect_ratio": row["aspect_ratio"],
            "beats": json.loads(row["timeline_json"]),
            "version": row["version"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def create(
        self,
        owner_user_id: str,
        analysis_id: UUID,
        asset_id: UUID,
        duration_seconds: int,
        aspect_ratio: str,
        beats: list[dict[str, object]],
    ) -> dict[str, object]:
        validated = TimelineDraftUpdate(
            expected_version=1,
            duration_seconds=duration_seconds,
            aspect_ratio=aspect_ratio,
            beats=beats,
        )
        timeline_json = json.dumps(
            [beat.model_dump(mode="json") for beat in validated.beats],
            ensure_ascii=False,
            separators=(",", ":"),
        )
        if len(timeline_json.encode("utf-8")) > self.MAX_TIMELINE_BYTES:
            raise ValueError("Timeline payload exceeds the storage limit")
        draft_id = str(uuid4())
        now = self._now()
        try:
            with self.tasks._connection() as connection:
                connection.execute(
                    """INSERT INTO video_timeline_drafts (
                        draft_id, owner_user_id, analysis_id, asset_id,
                        duration_seconds, aspect_ratio, timeline_json, version,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?)""",
                    (
                        draft_id, owner_user_id, str(analysis_id), str(asset_id),
                        duration_seconds, aspect_ratio, timeline_json, now, now,
                    ),
                )
                row = connection.execute(
                    """SELECT * FROM video_timeline_drafts
                       WHERE draft_id = ? AND owner_user_id = ?""",
                    (draft_id, owner_user_id),
                ).fetchone()
        except sqlite3.IntegrityError as exc:
            raise TimelineConflict("A draft already exists for this analysis asset") from exc
        if row is None:
            raise RuntimeError("Created timeline draft could not be read back")
        return self._record(row)

    def get(self, owner_user_id: str, draft_id: UUID) -> dict[str, object] | None:
        with self.tasks._connection() as connection:
            row = connection.execute(
                """SELECT * FROM video_timeline_drafts
                   WHERE draft_id = ? AND owner_user_id = ?""",
                (str(draft_id), owner_user_id),
            ).fetchone()
        return self._record(row) if row is not None else None

    def update(
        self,
        owner_user_id: str,
        draft_id: UUID,
        update: TimelineDraftUpdate,
    ) -> dict[str, object] | None:
        timeline_json = json.dumps(
            [beat.model_dump(mode="json") for beat in update.beats],
            ensure_ascii=False,
            separators=(",", ":"),
        )
        if len(timeline_json.encode("utf-8")) > self.MAX_TIMELINE_BYTES:
            raise ValueError("Timeline payload exceeds the storage limit")
        now = self._now()
        with self.tasks._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                """UPDATE video_timeline_drafts
                   SET duration_seconds = ?, aspect_ratio = ?, timeline_json = ?,
                       version = version + 1, updated_at = ?
                   WHERE draft_id = ? AND owner_user_id = ? AND version = ?""",
                (
                    update.duration_seconds, update.aspect_ratio, timeline_json,
                    now, str(draft_id), owner_user_id, update.expected_version,
                ),
            )
            if cursor.rowcount != 1:
                exists = connection.execute(
                    """SELECT 1 FROM video_timeline_drafts
                       WHERE draft_id = ? AND owner_user_id = ?""",
                    (str(draft_id), owner_user_id),
                ).fetchone()
                if exists is None:
                    return None
                raise TimelineConflict("Timeline draft version is stale")
            row = connection.execute(
                """SELECT * FROM video_timeline_drafts
                   WHERE draft_id = ? AND owner_user_id = ?""",
                (str(draft_id), owner_user_id),
            ).fetchone()
        return self._record(row) if row is not None else None
