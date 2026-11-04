"""Owner-scoped editable video timeline drafts with optimistic concurrency."""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from mrhub.infrastructure.database import TaskRepository
from mrhub.video_intelligence.jobs import VideoAnalysisJobRepository
from mrhub.video_intelligence.timeline import VideoTimeline


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
    def validate_interval(self) -> TimelineBeat:
        if self.end_seconds <= self.start_seconds:
            raise ValueError("Timeline beat end must be after its start")
        return self


class TimelineDraftUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    expected_version: int = Field(ge=1)
    duration_seconds: int = Field(ge=3, le=60)
    aspect_ratio: str = Field(pattern=r"^(9:16|16:9|1:1|4:5)$")
    beats: list[TimelineBeat] = Field(min_length=1, max_length=20)
    renderer_timeline: VideoTimeline | None = None

    @model_validator(mode="after")
    def validate_timeline(self) -> TimelineDraftUpdate:
        previous_end = 0.0
        for beat in self.beats:
            if beat.end_seconds > self.duration_seconds:
                raise ValueError("Timeline beat exceeds draft duration")
            if beat.start_seconds < previous_end:
                raise ValueError("Timeline beats must be ordered and cannot overlap")
            previous_end = beat.end_seconds
        if self.renderer_timeline is not None:
            if self.renderer_timeline.requested_duration_seconds != self.duration_seconds:
                raise ValueError("Renderer timeline duration must match the draft duration")
            if self.renderer_timeline.output_aspect_ratio != self.aspect_ratio:
                raise ValueError("Renderer timeline aspect ratio must match the draft")
        return self



def validate_renderer_timeline_source_bounds(
    timeline: VideoTimeline, assets: list[object]
) -> None:
    """Require every clip interval to fit its analyzed source media duration."""
    source_durations: dict[str, float] = {}
    for item in assets:
        if not isinstance(item, dict):
            continue
        asset_id = item.get("asset_id")
        metadata = item.get("technical_metadata")
        if not isinstance(asset_id, str) or not isinstance(metadata, dict):
            continue
        raw_duration = metadata.get("duration_seconds")
        if isinstance(raw_duration, bool) or not isinstance(raw_duration, (int, float)):
            continue
        duration = float(raw_duration)
        if math.isfinite(duration) and duration > 0:
            source_durations[asset_id] = duration

    for clip in timeline.video_track:
        source_duration = source_durations.get(clip.source_asset_id)
        if source_duration is None:
            raise ValueError("Renderer timeline source duration is unavailable")
        if clip.source_end_seconds > source_duration + 0.001:
            raise ValueError("Renderer timeline source interval exceeds source duration")


class VideoTimelineDraftRepository:
    """Persist bounded editable timelines with owner checks and version fencing."""

    MAX_TIMELINE_BYTES = 60_000
    MAX_RENDERER_TIMELINE_BYTES = 100_000

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self.tasks = TaskRepository(database_path)
        self.tasks.initialize()

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()

    @staticmethod
    def _canonical_renderer_timeline(timeline: VideoTimeline) -> str:
        return json.dumps(
            timeline.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )

    def _validate_renderer_timeline(
        self,
        owner_user_id: str,
        analysis_id: str,
        asset_id: str,
        timeline: VideoTimeline,
    ) -> tuple[str, str]:
        analysis = VideoAnalysisJobRepository(self.database_path).get(
            owner_user_id, UUID(analysis_id)
        )
        if (
            analysis is None
            or analysis["status"] != "completed"
            or not isinstance(analysis.get("result"), dict)
        ):
            raise ValueError("Renderer timeline requires a completed owned analysis")
        assets = analysis["result"].get("assets")
        if not isinstance(assets, list):
            raise TypeError("Completed analysis source assets are unavailable")
        allowed_asset_ids = {
            str(item["asset_id"])
            for item in assets
            if isinstance(item, dict) and item.get("asset_id")
        }
        referenced_asset_ids = {clip.source_asset_id for clip in timeline.video_track}
        if (
            not referenced_asset_ids
            or not referenced_asset_ids.issubset(allowed_asset_ids)
            or asset_id not in referenced_asset_ids
        ):
            raise ValueError("Renderer timeline references an asset outside the draft analysis")
        validate_renderer_timeline_source_bounds(timeline, assets)
        encoded = self._canonical_renderer_timeline(timeline)
        if len(encoded.encode("utf-8")) > self.MAX_RENDERER_TIMELINE_BYTES:
            raise ValueError("Renderer timeline exceeds the storage limit")
        digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
        return encoded, digest

    @staticmethod
    def _record(row: sqlite3.Row) -> dict[str, object]:
        renderer_timeline_json = row["renderer_timeline_json"]
        return {
            "draft_id": row["draft_id"],
            "analysis_id": row["analysis_id"],
            "asset_id": row["asset_id"],
            "duration_seconds": row["duration_seconds"],
            "aspect_ratio": row["aspect_ratio"],
            "beats": json.loads(row["timeline_json"]),
            "renderer_timeline": (
                json.loads(renderer_timeline_json)
                if renderer_timeline_json is not None
                else None
            ),
            "renderer_timeline_sha256": row["renderer_timeline_sha256"],
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

        with self.tasks._connection() as connection:
            current = connection.execute(
                """SELECT analysis_id, asset_id, version
                   FROM video_timeline_drafts
                   WHERE draft_id = ? AND owner_user_id = ?""",
                (str(draft_id), owner_user_id),
            ).fetchone()
        if current is None:
            return None
        if int(current["version"]) != update.expected_version:
            raise TimelineConflict("Timeline draft version is stale")

        renderer_timeline_json = None
        renderer_timeline_sha256 = None
        if update.renderer_timeline is not None:
            renderer_timeline_json, renderer_timeline_sha256 = (
                self._validate_renderer_timeline(
                    owner_user_id,
                    str(current["analysis_id"]),
                    str(current["asset_id"]),
                    update.renderer_timeline,
                )
            )

        now = self._now()
        with self.tasks._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                """UPDATE video_timeline_drafts
                   SET duration_seconds = ?, aspect_ratio = ?, timeline_json = ?,
                       renderer_timeline_json = ?, renderer_timeline_sha256 = ?,
                       version = version + 1, updated_at = ?
                   WHERE draft_id = ? AND owner_user_id = ? AND version = ?""",
                (
                    update.duration_seconds, update.aspect_ratio, timeline_json,
                    renderer_timeline_json, renderer_timeline_sha256, now,
                    str(draft_id), owner_user_id, update.expected_version,
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
