from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from mrhub.api.routes import video_intelligence
from mrhub.security.auth import AuthenticatedUser
from mrhub.video_intelligence.schemas import BrandIdentity, VideoTechnicalMetadata


def test_video_metadata_endpoint_uses_only_owner_scoped_video_asset(monkeypatch, tmp_path):
    asset_id = uuid4()
    expected_path = tmp_path / "internal-video.mp4"
    calls = {}

    class FakeMediaRepository:
        def __init__(self, _database_path):
            pass

        def get(self, owner_user_id, requested_asset_id):
            calls["owner"] = owner_user_id
            calls["asset_id"] = requested_asset_id
            return {
                "asset_id": str(asset_id),
                "media_type": "video/mp4",
                "storage_key": "internal-storage-key.mp4",
            } if owner_user_id == "owner-a" else None

        def file_path(self, storage_key):
            calls["storage_key"] = storage_key
            return expected_path

    def fake_probe(path):
        calls["path"] = path
        return VideoTechnicalMetadata(
            duration_seconds=12.5,
            width=1920,
            height=1080,
            frame_rate=30,
            codec="h264",
            has_audio=True,
            metadata_status="available",
        )

    monkeypatch.setattr(
        video_intelligence, "get_settings",
        lambda: SimpleNamespace(database_path=tmp_path / "app.sqlite"),
    )
    monkeypatch.setattr(video_intelligence, "MediaAssetRepository", FakeMediaRepository)
    monkeypatch.setattr(video_intelligence, "probe_video", fake_probe)

    result = video_intelligence.inspect_video_asset(
        asset_id,
        AuthenticatedUser(user_id="owner-a", username="owner"),
    )

    assert result.width == 1920
    assert result.metadata_status == "available"
    assert calls["owner"] == "owner-a"
    assert calls["asset_id"] == asset_id
    assert calls["storage_key"] == "internal-storage-key.mp4"
    assert calls["path"] == expected_path


def test_video_metadata_endpoint_hides_assets_owned_by_other_users(monkeypatch, tmp_path):
    class FakeMediaRepository:
        def __init__(self, _database_path):
            pass

        def get(self, _owner_user_id, _asset_id):
            return None

    monkeypatch.setattr(
        video_intelligence, "get_settings",
        lambda: SimpleNamespace(database_path=tmp_path / "app.sqlite"),
    )
    monkeypatch.setattr(video_intelligence, "MediaAssetRepository", FakeMediaRepository)

    with pytest.raises(HTTPException) as error:
        video_intelligence.inspect_video_asset(
            uuid4(),
            AuthenticatedUser(user_id="owner-b", username="other"),
        )
    assert error.value.status_code == 404


def test_video_metadata_endpoint_rejects_non_video_assets(monkeypatch, tmp_path):
    class FakeMediaRepository:
        def __init__(self, _database_path):
            pass

        def get(self, _owner_user_id, asset_id):
            return {"asset_id": str(asset_id), "media_type": "image/png", "storage_key": "image.png"}

    monkeypatch.setattr(
        video_intelligence, "get_settings",
        lambda: SimpleNamespace(database_path=tmp_path / "app.sqlite"),
    )
    monkeypatch.setattr(video_intelligence, "MediaAssetRepository", FakeMediaRepository)

    with pytest.raises(HTTPException) as error:
        video_intelligence.inspect_video_asset(
            uuid4(),
            AuthenticatedUser(user_id="owner-a", username="owner"),
        )
    assert error.value.status_code == 415


def test_analysis_brand_logo_must_be_owner_scoped_image(monkeypatch, tmp_path):
    logo_id = uuid4()
    calls = {}

    class FakeMediaRepository:
        def __init__(self, _database_path):
            pass

        def get(self, owner_user_id, asset_id):
            calls["owner_user_id"] = owner_user_id
            calls["asset_id"] = asset_id

    monkeypatch.setattr(
        video_intelligence,
        "get_settings",
        lambda: SimpleNamespace(database_path=tmp_path / "app.sqlite"),
    )
    monkeypatch.setattr(video_intelligence, "MediaAssetRepository", FakeMediaRepository)

    with pytest.raises(HTTPException) as error:
        video_intelligence._validate_logo(
            "owner-a",
            BrandIdentity(brand_name="Example", logo_asset_id=str(logo_id)),
        )

    assert error.value.status_code == 422
    assert calls == {"owner_user_id": "owner-a", "asset_id": logo_id}


def test_analysis_brand_logo_rejects_non_image_assets(monkeypatch, tmp_path):
    logo_id = uuid4()

    class FakeMediaRepository:
        def __init__(self, _database_path):
            pass

        def get(self, owner_user_id, asset_id):
            assert owner_user_id == "owner-a"
            assert asset_id == logo_id
            return {"media_type": "video/mp4"}

    monkeypatch.setattr(
        video_intelligence,
        "get_settings",
        lambda: SimpleNamespace(database_path=tmp_path / "app.sqlite"),
    )
    monkeypatch.setattr(video_intelligence, "MediaAssetRepository", FakeMediaRepository)

    with pytest.raises(HTTPException) as error:
        video_intelligence._validate_logo(
            "owner-a",
            BrandIdentity(brand_name="Example", logo_asset_id=str(logo_id)),
        )

    assert error.value.status_code == 422


def test_cancel_video_analysis_endpoint_returns_owner_scoped_result(monkeypatch):
    analysis_id = uuid4()
    calls = {}

    class FakeJobs:
        def cancel(self, owner_user_id, requested_id):
            calls["owner"] = owner_user_id
            calls["analysis_id"] = requested_id
            return {
                "analysis_id": str(analysis_id),
                "status": "cancelled",
                "cancellation_requested": False,
            }

    monkeypatch.setattr(video_intelligence, "_analysis_jobs", FakeJobs)
    result = video_intelligence.cancel_video_analysis(
        analysis_id,
        AuthenticatedUser(user_id="owner-a", username="owner"),
    )
    assert result["status"] == "cancelled"
    assert calls == {"owner": "owner-a", "analysis_id": analysis_id}


def test_cancel_video_analysis_endpoint_hides_non_owned_analysis(monkeypatch):
    class FakeJobs:
        def cancel(self, _owner_user_id, _analysis_id):
            return None

    monkeypatch.setattr(video_intelligence, "_analysis_jobs", FakeJobs)
    with pytest.raises(HTTPException) as error:
        video_intelligence.cancel_video_analysis(
            uuid4(),
            AuthenticatedUser(user_id="owner-b", username="other"),
        )
    assert error.value.status_code == 404


def test_cancel_video_analysis_endpoint_maps_conflict_to_409(monkeypatch):
    from mrhub.video_intelligence.jobs import VideoAnalysisConflict

    class FakeJobs:
        def cancel(self, _owner_user_id, _analysis_id):
            raise VideoAnalysisConflict("not cancellable")

    monkeypatch.setattr(video_intelligence, "_analysis_jobs", FakeJobs)
    with pytest.raises(HTTPException) as error:
        video_intelligence.cancel_video_analysis(
            uuid4(),
            AuthenticatedUser(user_id="owner-a", username="owner"),
        )
    assert error.value.status_code == 409


def test_create_timeline_draft_requires_owner_completed_analysis_and_asset(monkeypatch, tmp_path):
    from mrhub.api.routes.video_intelligence import TimelineDraftCreateRequest

    analysis_id = uuid4()
    asset_id = uuid4()
    calls = {}

    class FakeJobs:
        def get(self, owner_user_id, requested_id):
            calls["owner"] = owner_user_id
            calls["analysis_id"] = requested_id
            return {
                "status": "completed",
                "result": {"assets": [{"asset_id": str(asset_id)}]},
            }

    class FakeDrafts:
        def create(self, *args):
            calls["create_args"] = args
            return {"draft_id": "draft-1", "version": 1}

    monkeypatch.setattr(video_intelligence, "_analysis_jobs", FakeJobs)
    monkeypatch.setattr(video_intelligence, "_timeline_drafts", FakeDrafts)
    result = video_intelligence.create_timeline_draft(
        TimelineDraftCreateRequest(
            analysis_id=analysis_id,
            asset_id=asset_id,
            duration_seconds=10,
            aspect_ratio="9:16",
            beats=[{
                "start_seconds": 0,
                "end_seconds": 10,
                "generation_instruction": "Create an original scene",
            }],
        ),
        AuthenticatedUser(user_id="owner-a", username="owner"),
    )

    assert result["draft_id"] == "draft-1"
    assert calls["owner"] == "owner-a"
    assert calls["analysis_id"] == analysis_id
    assert calls["create_args"][0] == "owner-a"


def test_create_timeline_draft_hides_asset_outside_analysis(monkeypatch):
    from mrhub.api.routes.video_intelligence import TimelineDraftCreateRequest

    class FakeJobs:
        def get(self, _owner_user_id, _analysis_id):
            return {"status": "completed", "result": {"assets": []}}

    monkeypatch.setattr(video_intelligence, "_analysis_jobs", FakeJobs)
    with pytest.raises(HTTPException) as error:
        video_intelligence.create_timeline_draft(
            TimelineDraftCreateRequest(
                analysis_id=uuid4(),
                asset_id=uuid4(),
                duration_seconds=10,
                aspect_ratio="9:16",
                beats=[{
                    "start_seconds": 0,
                    "end_seconds": 10,
                    "generation_instruction": "Create an original scene",
                }],
            ),
            AuthenticatedUser(user_id="owner-a", username="owner"),
        )
    assert error.value.status_code == 404


def test_get_and_update_timeline_draft_are_owner_scoped(monkeypatch):
    from mrhub.video_intelligence.timeline_drafts import TimelineDraftUpdate

    draft_id = uuid4()
    calls = {}

    class FakeDrafts:
        def get(self, owner_user_id, requested_id):
            calls["get"] = (owner_user_id, requested_id)
            return {"draft_id": str(draft_id), "version": 1} if owner_user_id == "owner-a" else None

        def update(self, owner_user_id, requested_id, payload):
            calls["update"] = (owner_user_id, requested_id, payload.expected_version)
            return {"draft_id": str(draft_id), "version": 2} if owner_user_id == "owner-a" else None

    monkeypatch.setattr(video_intelligence, "_timeline_drafts", FakeDrafts)
    user = AuthenticatedUser(user_id="owner-a", username="owner")
    assert video_intelligence.get_timeline_draft(draft_id, user)["version"] == 1
    update = TimelineDraftUpdate(
        expected_version=1,
        duration_seconds=10,
        aspect_ratio="9:16",
        beats=[{
            "start_seconds": 0,
            "end_seconds": 10,
            "generation_instruction": "Edited original scene",
        }],
    )
    assert video_intelligence.update_timeline_draft(draft_id, update, user)["version"] == 2
    assert calls["get"] == ("owner-a", draft_id)
    assert calls["update"] == ("owner-a", draft_id, 1)

