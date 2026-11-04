"""Durable owner-scoped persistence for immutable video render snapshots."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from mrhub.infrastructure.database import TaskRepository
from mrhub.video_intelligence.jobs import VideoAnalysisJobRepository
from mrhub.video_intelligence.render_snapshot import VideoRenderTimelineSnapshot
from mrhub.video_intelligence.timeline_drafts import validate_renderer_timeline_source_bounds


class VideoRenderSnapshotConflict(ValueError):
    """Raised when a draft revision already has a different immutable snapshot."""


class VideoRenderSnapshotRepository:
    """Persist and retrieve immutable, owner-bound renderer timeline snapshots."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self.tasks = TaskRepository(database_path)
        self.tasks.initialize()

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()

    @staticmethod
    def _from_row(row: sqlite3.Row) -> VideoRenderTimelineSnapshot:
        return VideoRenderTimelineSnapshot(
            snapshot_version=row["snapshot_version"],
            snapshot_id=UUID(row["snapshot_id"]),
            owner_user_id=row["owner_user_id"],
            analysis_id=UUID(row["analysis_id"]),
            draft_id=UUID(row["draft_id"]),
            draft_version=row["draft_version"],
            timeline_json=row["timeline_json"],
            timeline_sha256=row["timeline_sha256"],
        )

    def create(
        self, snapshot: VideoRenderTimelineSnapshot
    ) -> tuple[VideoRenderTimelineSnapshot, bool]:
        """Insert a snapshot for the exact current draft revision, or replay it."""
        analysis = VideoAnalysisJobRepository(self.database_path).get(
            snapshot.owner_user_id, snapshot.analysis_id
        )
        if (
            analysis is None
            or analysis["status"] != "completed"
            or not isinstance(analysis.get("result"), dict)
        ):
            raise ValueError("Snapshot analysis must be completed and owned by the caller")

        assets = analysis["result"].get("assets")
        if not isinstance(assets, list):
            raise TypeError("Snapshot analysis assets are unavailable")
        allowed_asset_ids = {
            str(item["asset_id"])
            for item in assets
            if isinstance(item, dict) and item.get("asset_id")
        }
        timeline = snapshot.validated_timeline()
        referenced_asset_ids = {clip.source_asset_id for clip in timeline.video_track}
        if not referenced_asset_ids or not referenced_asset_ids.issubset(allowed_asset_ids):
            raise ValueError("Snapshot references an asset outside the completed analysis")
        validate_renderer_timeline_source_bounds(timeline, assets)

        now = self._now()
        with self.tasks._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            draft = connection.execute(
                """SELECT analysis_id, asset_id, version,
                          renderer_timeline_json, renderer_timeline_sha256
                   FROM video_timeline_drafts
                   WHERE draft_id = ? AND owner_user_id = ?""",
                (str(snapshot.draft_id), snapshot.owner_user_id),
            ).fetchone()
            existing = connection.execute(
                """SELECT * FROM video_render_timeline_snapshots
                   WHERE draft_id = ? AND draft_version = ?""",
                (str(snapshot.draft_id), snapshot.draft_version),
            ).fetchone()
            if existing is not None:
                stored = self._from_row(existing)
                if (
                    stored.owner_user_id != snapshot.owner_user_id
                    or stored.analysis_id != snapshot.analysis_id
                    or stored.timeline_sha256 != snapshot.timeline_sha256
                    or stored.timeline_json != snapshot.timeline_json
                ):
                    raise VideoRenderSnapshotConflict(
                        "Draft revision already has a different immutable snapshot"
                    )
                return stored, False

            if (
                draft is None
                or draft["analysis_id"] != str(snapshot.analysis_id)
                or int(draft["version"]) != snapshot.draft_version
                or str(draft["asset_id"]) not in referenced_asset_ids
                or draft["renderer_timeline_json"] != snapshot.timeline_json
                or draft["renderer_timeline_sha256"] != snapshot.timeline_sha256
            ):
                raise VideoRenderSnapshotConflict(
                    "Snapshot does not match the current owner-scoped draft revision"
                )

            connection.execute(
                """INSERT INTO video_render_timeline_snapshots (
                    snapshot_id, owner_user_id, analysis_id, draft_id,
                    draft_version, snapshot_version, timeline_json,
                    timeline_sha256, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    str(snapshot.snapshot_id),
                    snapshot.owner_user_id,
                    str(snapshot.analysis_id),
                    str(snapshot.draft_id),
                    snapshot.draft_version,
                    snapshot.snapshot_version,
                    snapshot.timeline_json,
                    snapshot.timeline_sha256,
                    now,
                ),
            )
            row = connection.execute(
                """SELECT * FROM video_render_timeline_snapshots
                   WHERE snapshot_id = ? AND owner_user_id = ?""",
                (str(snapshot.snapshot_id), snapshot.owner_user_id),
            ).fetchone()
            if row is None:
                raise RuntimeError("Inserted render snapshot could not be read back")
            return self._from_row(row), True

    def get(
        self, owner_user_id: str, snapshot_id: UUID
    ) -> VideoRenderTimelineSnapshot | None:
        """Read a snapshot only within its owner's namespace and revalidate its hash."""
        with self.tasks._connection() as connection:
            row = connection.execute(
                """SELECT * FROM video_render_timeline_snapshots
                   WHERE snapshot_id = ? AND owner_user_id = ?""",
                (str(snapshot_id), owner_user_id),
            ).fetchone()
        return self._from_row(row) if row is not None else None
