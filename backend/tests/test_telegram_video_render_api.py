import hashlib
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest
from fastapi import HTTPException

from mrhub.api.routes import telegram_integration as telegram_routes


def test_telegram_render_history_uses_bounded_owner_scoped_cursor_paging(monkeypatch):
    owner = "owner-a"
    first_id = UUID("11111111-1111-4111-8111-111111111111")
    second_id = UUID("22222222-2222-4222-8222-222222222222")
    first_time = "2026-11-16T10:00:00+00:00"
    second_time = "2026-11-15T10:00:00+00:00"
    rows = [
        {"render_id": str(first_id), "created_at": first_time},
        {"render_id": str(second_id), "created_at": second_time},
    ]
    calls = []

    class FakeRepository:
        def __init__(self, _database_path):
            pass

        def list_for_owner(self, owner_user_id, *, limit, before=None):
            calls.append((owner_user_id, limit, before))
            if before is None:
                return rows[:limit]
            return rows[1:2]

        def get(self, owner_user_id, render_id):
            assert owner_user_id == owner
            return {
                "render_id": str(render_id),
                "status": "completed",
                "output_asset_id": None,
                "error_code": None,
                "created_at": first_time,
                "updated_at": first_time,
            }

    monkeypatch.setattr(telegram_routes, "VideoRenderJobRepository", FakeRepository)
    monkeypatch.setattr(
        telegram_routes,
        "get_settings",
        lambda: SimpleNamespace(database_path=Path("unused.sqlite")),
    )
    identity = SimpleNamespace(owner_user_id=owner)

    first = telegram_routes.list_telegram_video_renders(identity, limit=1)
    assert first["count"] == 1
    assert first["renders"][0]["render_id"] == str(first_id)
    assert first["next_cursor"]
    assert calls[0][0:2] == (owner, 2)

    second = telegram_routes.list_telegram_video_renders(
        identity, limit=1, cursor=first["next_cursor"]
    )
    assert second["count"] == 1
    assert second["renders"][0]["render_id"] == str(second_id)
    assert second["next_cursor"] is None
    assert calls[1][2] == (first_time, first_id)


def test_telegram_render_history_rejects_invalid_cursor(monkeypatch):
    monkeypatch.setattr(
        telegram_routes,
        "get_settings",
        lambda: SimpleNamespace(database_path=Path("unused.sqlite")),
    )
    with pytest.raises(HTTPException) as error:
        telegram_routes.list_telegram_video_renders(
            SimpleNamespace(owner_user_id="owner-a"), cursor="not/a/cursor"
        )
    assert error.value.status_code == 422


def test_telegram_render_file_requires_completed_owner_asset_and_verified_mp4(
    tmp_path, monkeypatch
):
    render_id = UUID("33333333-3333-4333-8333-333333333333")
    asset_id = UUID("44444444-4444-4444-8444-444444444444")
    path = tmp_path / "private-render.mp4"
    content = b"\x00\x00\x00\x18ftypisom"
    path.write_bytes(content)
    digest = hashlib.sha256(content).hexdigest()
    calls = []

    class FakeRenderRepository:
        def __init__(self, _database_path):
            pass

        def get(self, owner_user_id, requested_render_id):
            calls.append(("render", owner_user_id, requested_render_id))
            return {
                "render_id": str(render_id),
                "status": "completed",
                "output_asset_id": str(asset_id),
            }

    class FakeMediaRepository:
        def __init__(self, _database_path):
            pass

        def get(self, owner_user_id, requested_asset_id):
            calls.append(("asset", owner_user_id, requested_asset_id))
            return {
                "asset_id": str(asset_id),
                "media_type": "video/mp4",
                "processing_status": "stored",
                "storage_key": "private-render.mp4",
                "file_size": len(content),
                "content_hash": digest,
            }

        def file_path(self, storage_key):
            assert storage_key == "private-render.mp4"
            return path

    monkeypatch.setattr(
        telegram_routes, "VideoRenderJobRepository", FakeRenderRepository
    )
    monkeypatch.setattr(
        telegram_routes, "MediaAssetRepository", FakeMediaRepository
    )
    monkeypatch.setattr(
        telegram_routes,
        "get_settings",
        lambda: SimpleNamespace(database_path=tmp_path / "hub.sqlite"),
    )

    response = telegram_routes.download_telegram_video_render(
        render_id, SimpleNamespace(owner_user_id="owner-a")
    )
    assert response.path == str(path)
    assert response.filename == f"render-{render_id}.mp4"
    assert response.media_type == "video/mp4"
    assert response.headers["cache-control"] == "private, no-store"
    assert calls == [
        ("render", "owner-a", render_id),
        ("asset", "owner-a", asset_id),
    ]


def test_telegram_render_file_rejects_missing_or_oversized_output(tmp_path, monkeypatch):
    render_id = UUID("55555555-5555-4555-8555-555555555555")
    asset_id = UUID("66666666-6666-4666-8666-666666666666")
    path = tmp_path / "large.mp4"
    content = b"\x00\x00\x00\x18ftypisom" + (b"x" * 32)
    path.write_bytes(content)

    class FakeRenderRepository:
        def __init__(self, _database_path):
            pass

        def get(self, _owner_user_id, _render_id):
            return {"status": "completed", "output_asset_id": str(asset_id)}

    class FakeMediaRepository:
        def __init__(self, _database_path):
            pass

        def get(self, _owner_user_id, _asset_id):
            return {
                "media_type": "video/mp4",
                "processing_status": "processed",
                "storage_key": "large.mp4",
                "file_size": len(content),
                "content_hash": hashlib.sha256(content).hexdigest(),
            }

        def file_path(self, _storage_key):
            return path

    monkeypatch.setattr(telegram_routes, "VideoRenderJobRepository", FakeRenderRepository)
    monkeypatch.setattr(telegram_routes, "MediaAssetRepository", FakeMediaRepository)
    monkeypatch.setattr(
        telegram_routes,
        "get_settings",
        lambda: SimpleNamespace(database_path=tmp_path / "hub.sqlite"),
    )
    monkeypatch.setattr(telegram_routes, "MAX_TELEGRAM_VIDEO_BYTES", 20)

    with pytest.raises(HTTPException) as error:
        telegram_routes.download_telegram_video_render(
            render_id, SimpleNamespace(owner_user_id="owner-a")
        )
    assert error.value.status_code == 413
    assert error.value.detail["code"] == "telegram_video_render_too_large"
