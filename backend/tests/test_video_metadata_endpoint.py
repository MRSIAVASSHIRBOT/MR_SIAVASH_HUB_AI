from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from mrhub.api.routes import video_intelligence
from mrhub.security.auth import AuthenticatedUser
from mrhub.video_intelligence.schemas import VideoTechnicalMetadata


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
