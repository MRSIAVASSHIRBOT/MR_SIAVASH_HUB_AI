from uuid import UUID

import pytest
from pydantic import ValidationError

from mrhub.video_intelligence.timeline_drafts import (
    TimelineConflict,
    TimelineDraftUpdate,
    VideoTimelineDraftRepository,
)


def _repository(tmp_path):
    repository = VideoTimelineDraftRepository(tmp_path / "timeline-drafts.sqlite")
    repository.tasks.create_auth_user("owner-a", "owner-a", "salt-a", "hash-a")
    repository.tasks.create_auth_user("owner-b", "owner-b", "salt-b", "hash-b")
    with repository.tasks._connection() as connection:
        connection.execute(
            """INSERT INTO tasks (
                task_id, task_type, status, risk_class, created_at, updated_at, description
            ) VALUES ('task-a', 'video.analysis', 'completed', 'low', 'now', 'now', 'test')"""
        )
        connection.execute(
            """INSERT INTO video_analysis_runs (
                analysis_id, task_id, owner_user_id, mode, status,
                result_json, error_code, created_at, updated_at
            ) VALUES ('11111111-1111-4111-8111-111111111111', 'task-a',
                'owner-a', 'faithful_style_reconstruction', 'completed',
                '{"assets":[{"asset_id":"22222222-2222-4222-8222-222222222222"}]}',
                NULL, 'now', 'now')"""
        )
    return repository


def _beats():
    return [
        {
            "start_seconds": 0.0,
            "end_seconds": 4.0,
            "generation_instruction": "Create an original opening scene",
            "transition_to_next": "match cut",
            "source_timestamp_seconds": 0.0,
            "confidence": 0.9,
        },
        {
            "start_seconds": 4.0,
            "end_seconds": 10.0,
            "generation_instruction": "Continue with an original detail scene",
            "transition_to_next": "fade",
            "source_timestamp_seconds": 5.0,
            "confidence": 0.8,
        },
    ]


def _create(repository):
    return repository.create(
        "owner-a",
        UUID("11111111-1111-4111-8111-111111111111"),
        UUID("22222222-2222-4222-8222-222222222222"),
        10,
        "9:16",
        _beats(),
    )


def test_timeline_draft_is_owner_scoped_and_persisted(tmp_path):
    repository = _repository(tmp_path)
    created = _create(repository)
    draft_id = UUID(created["draft_id"])

    assert created["version"] == 1
    assert len(created["beats"]) == 2
    assert repository.get("owner-a", draft_id)["beats"][1]["start_seconds"] == 4.0
    assert repository.get("owner-b", draft_id) is None


def test_timeline_draft_update_uses_optimistic_version_fencing(tmp_path):
    repository = _repository(tmp_path)
    created = _create(repository)
    draft_id = UUID(created["draft_id"])
    update = TimelineDraftUpdate(
        expected_version=1,
        duration_seconds=12,
        aspect_ratio="16:9",
        beats=[
            {
                **_beats()[0],
                "end_seconds": 5.0,
                "transition_to_next": "hard cut",
            },
            {
                **_beats()[1],
                "start_seconds": 5.0,
                "end_seconds": 12.0,
            },
        ],
    )

    saved = repository.update("owner-a", draft_id, update)

    assert saved["version"] == 2
    assert saved["duration_seconds"] == 12
    assert saved["aspect_ratio"] == "16:9"
    assert saved["beats"][0]["end_seconds"] == 5.0
    with pytest.raises(TimelineConflict):
        repository.update("owner-a", draft_id, update)
    assert repository.get("owner-a", draft_id)["version"] == 2


def test_timeline_draft_update_hides_non_owned_drafts(tmp_path):
    repository = _repository(tmp_path)
    created = _create(repository)
    draft_id = UUID(created["draft_id"])
    update = TimelineDraftUpdate(
        expected_version=1,
        duration_seconds=10,
        aspect_ratio="9:16",
        beats=_beats(),
    )

    assert repository.update("owner-b", draft_id, update) is None
    assert repository.get("owner-a", draft_id)["version"] == 1


@pytest.mark.parametrize(
    "beats",
    [
        [
            {"start_seconds": 0, "end_seconds": 7, "generation_instruction": "A"},
            {"start_seconds": 6, "end_seconds": 10, "generation_instruction": "B"},
        ],
        [{"start_seconds": 0, "end_seconds": 11, "generation_instruction": "Too long"}],
        [{"start_seconds": 4, "end_seconds": 3, "generation_instruction": "Invalid"}],
    ],
)
def test_timeline_draft_rejects_overlapping_or_out_of_bounds_intervals(beats):
    with pytest.raises(ValidationError):
        TimelineDraftUpdate(
            expected_version=1,
            duration_seconds=10,
            aspect_ratio="9:16",
            beats=beats,
        )


def test_timeline_draft_rejects_empty_or_oversized_timeline():
    with pytest.raises(ValidationError):
        TimelineDraftUpdate(
            expected_version=1,
            duration_seconds=10,
            aspect_ratio="9:16",
            beats=[],
        )



def test_timeline_draft_list_is_owner_and_analysis_scoped(tmp_path):
    repository = _repository(tmp_path)
    created = _create(repository)
    analysis_id = UUID(created["analysis_id"])

    owned = repository.list_for_analysis("owner-a", analysis_id)
    foreign_owner = repository.list_for_analysis("owner-b", analysis_id)
    foreign_analysis = repository.list_for_analysis(
        "owner-a", UUID("99999999-9999-4999-8999-999999999999")
    )

    assert [item["draft_id"] for item in owned] == [created["draft_id"]]
    assert foreign_owner == []
    assert foreign_analysis == []
