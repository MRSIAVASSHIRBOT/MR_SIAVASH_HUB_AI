"""Immutable, owner-bound render timeline snapshots.

Snapshots store canonical validated renderer input rather than a mutable draft
reference. Workers can verify the content hash and identity before opening media.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from mrhub.video_intelligence.timeline import VideoTimeline


def _canonical_timeline_json(timeline: VideoTimeline) -> str:
    return json.dumps(
        timeline.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


class VideoRenderTimelineSnapshot(BaseModel):
    """Content-addressed immutable input for one owner-scoped render job."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        allow_inf_nan=False,
    )

    snapshot_version: Literal["1"] = "1"
    snapshot_id: UUID = Field(default_factory=uuid4)
    owner_user_id: str = Field(min_length=1, max_length=200)
    analysis_id: UUID
    draft_id: UUID
    draft_version: int = Field(ge=1, strict=True)
    timeline_json: str = Field(min_length=2, max_length=100_000)
    timeline_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def validate_canonical_timeline_and_hash(self) -> VideoRenderTimelineSnapshot:
        encoded = self.timeline_json.encode("utf-8")
        if len(encoded) > 100_000:
            raise ValueError("Render timeline snapshot exceeds the storage limit")
        try:
            timeline = VideoTimeline.model_validate_json(self.timeline_json)
        except (TypeError, ValueError) as exc:
            raise ValueError("Render timeline snapshot is invalid") from exc
        canonical = _canonical_timeline_json(timeline)
        if canonical != self.timeline_json:
            raise ValueError("Render timeline snapshot must use canonical JSON")
        digest = hashlib.sha256(encoded).hexdigest()
        if digest != self.timeline_sha256:
            raise ValueError("Render timeline snapshot hash does not match its content")
        return self

    @classmethod
    def create(
        cls,
        *,
        owner_user_id: str,
        analysis_id: UUID,
        draft_id: UUID,
        draft_version: int,
        timeline: VideoTimeline,
        analysis_source_asset_ids: Iterable[str],
    ) -> VideoRenderTimelineSnapshot:
        """Create a snapshot only when every referenced source belongs to analysis."""
        allowed_sources = set(analysis_source_asset_ids)
        referenced_sources = {clip.source_asset_id for clip in timeline.video_track}
        if not referenced_sources or not referenced_sources.issubset(allowed_sources):
            raise ValueError("Render timeline references a source outside the analysis")
        canonical = _canonical_timeline_json(timeline)
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        return cls(
            owner_user_id=owner_user_id,
            analysis_id=analysis_id,
            draft_id=draft_id,
            draft_version=draft_version,
            timeline_json=canonical,
            timeline_sha256=digest,
        )

    def validated_timeline(self) -> VideoTimeline:
        """Return a fresh validated model; callers cannot mutate stored snapshot data."""
        return VideoTimeline.model_validate_json(self.timeline_json)

    def idempotency_digest(self) -> str:
        """Bind retries to the exact immutable draft revision and timeline content."""
        identity = {
            "analysis_id": str(self.analysis_id),
            "draft_id": str(self.draft_id),
            "draft_version": self.draft_version,
            "owner_user_id": self.owner_user_id,
            "snapshot_version": self.snapshot_version,
            "timeline_sha256": self.timeline_sha256,
        }
        canonical = json.dumps(
            identity,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()
