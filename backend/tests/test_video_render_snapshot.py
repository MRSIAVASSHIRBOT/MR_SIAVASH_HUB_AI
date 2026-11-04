import hashlib
from uuid import UUID

from pydantic import ValidationError
import pytest

from mrhub.video_intelligence.render_snapshot import VideoRenderTimelineSnapshot
from mrhub.video_intelligence.timeline import VideoTimeline


OWNER = "owner-a"
ANALYSIS_ID = UUID("11111111-1111-4111-8111-111111111111")
DRAFT_ID = UUID("33333333-3333-4333-8333-333333333333")
SOURCE_ID = "22222222-2222-4222-8222-222222222222"


def _timeline() -> VideoTimeline:
    return VideoTimeline(
        output_aspect_ratio="9:16",
        requested_duration_seconds=5,
        actual_duration_seconds=5,
        duration_shortfall_seconds=0,
        audio_analysis_status="not_requested",
        audio_render_status="not_implemented",
        timeline_status="validated_cut_only",
        render_status="not_implemented",
        video_track=[
            {
                "clip_id": "clip-001",
                "source_asset_id": SOURCE_ID,
                "source_scene_index": 0,
                "source_start_seconds": 1,
                "source_end_seconds": 6,
                "timeline_start_seconds": 0,
                "timeline_end_seconds": 5,
                "transition_in": "none",
            }
        ],
    )


def _snapshot(**overrides) -> VideoRenderTimelineSnapshot:
    values = {
        "owner_user_id": OWNER,
        "analysis_id": ANALYSIS_ID,
        "draft_id": DRAFT_ID,
        "draft_version": 3,
        "timeline": _timeline(),
        "analysis_source_asset_ids": [SOURCE_ID],
    }
    values.update(overrides)
    return VideoRenderTimelineSnapshot.create(**values)


def test_snapshot_preserves_renderer_mapping_and_owner_identity():
    snapshot = _snapshot()

    assert snapshot.owner_user_id == OWNER
    assert snapshot.analysis_id == ANALYSIS_ID
    assert snapshot.draft_id == DRAFT_ID
    assert snapshot.draft_version == 3
    assert snapshot.validated_timeline().video_track[0].source_asset_id == SOURCE_ID
    assert snapshot.validated_timeline().video_track[0].source_start_seconds == 1


def test_snapshot_rejects_source_assets_outside_completed_analysis():
    with pytest.raises(ValueError, match="source outside the analysis"):
        _snapshot(analysis_source_asset_ids=["another-source"])


def test_snapshot_hash_detects_content_tampering():
    snapshot = _snapshot()
    with pytest.raises(ValidationError, match="hash does not match"):
        VideoRenderTimelineSnapshot(
            snapshot_version=snapshot.snapshot_version,
            snapshot_id=snapshot.snapshot_id,
            owner_user_id=snapshot.owner_user_id,
            analysis_id=snapshot.analysis_id,
            draft_id=snapshot.draft_id,
            draft_version=snapshot.draft_version,
            timeline_json=snapshot.timeline_json.replace(
                '"source_start_seconds":1.0',
                '"source_start_seconds":2.0',
            ),
            timeline_sha256=snapshot.timeline_sha256,
        )


def test_snapshot_rejects_noncanonical_json_even_when_hash_matches():
    snapshot = _snapshot()
    noncanonical = snapshot.timeline_json.replace(",", ", ")
    digest = hashlib.sha256(noncanonical.encode("utf-8")).hexdigest()
    with pytest.raises(ValidationError, match="canonical JSON"):
        VideoRenderTimelineSnapshot(
            snapshot_version=snapshot.snapshot_version,
            snapshot_id=snapshot.snapshot_id,
            owner_user_id=snapshot.owner_user_id,
            analysis_id=snapshot.analysis_id,
            draft_id=snapshot.draft_id,
            draft_version=snapshot.draft_version,
            timeline_json=noncanonical,
            timeline_sha256=digest,
        )


def test_idempotency_digest_is_bound_to_draft_revision():
    snapshot = _snapshot()
    next_revision = _snapshot(draft_version=4)

    assert snapshot.idempotency_digest() != next_revision.idempotency_digest()
    assert snapshot.idempotency_digest() == _snapshot().idempotency_digest()


def test_snapshot_metadata_is_immutable():
    snapshot = _snapshot()
    with pytest.raises(ValidationError):
        snapshot.draft_version = 4


def test_snapshot_rejects_invalid_or_oversized_timeline_json():
    with pytest.raises(ValidationError):
        VideoRenderTimelineSnapshot(
            owner_user_id=OWNER,
            analysis_id=ANALYSIS_ID,
            draft_id=DRAFT_ID,
            draft_version=1,
            timeline_json="{}",
            timeline_sha256="0" * 64,
        )
