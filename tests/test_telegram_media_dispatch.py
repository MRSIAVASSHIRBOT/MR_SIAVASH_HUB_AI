from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

from client_helpers import authenticated_client
from mrhub.config import get_settings
from mrhub.content.dispatcher import ContentScheduleDispatcher, PublishReceipt
from mrhub.infrastructure.database import TaskRepository
from mrhub.media.repository import MediaAssetRepository


class CapturingMediaAdapter:
    def __init__(self):
        self.draft = None

    def publish(self, draft: dict[str, object], *, idempotency_key: str) -> PublishReceipt:
        self.draft = draft
        media = draft["media_asset"]
        assert isinstance(media, dict)
        assert Path(str(media["path"])).is_file()
        assert media["media_type"] == "image/png"
        assert idempotency_key
        return PublishReceipt(provider_post_id="media-provider-post-7")


def test_scheduled_dispatch_resolves_owned_media_and_passes_it_to_adapter():
    client = authenticated_client()
    upload = client.post(
        "/content/assets",
        content=b"\x89PNG\r\n\x1a\nmedia-dispatch-fixture",
        headers={"Content-Type": "image/png", "X-File-Name": "dispatch.png"},
    )
    assert upload.status_code == 201
    asset_id = upload.json()["asset_id"]

    created = client.post(
        "/content/drafts",
        json={
            "platform": "telegram",
            "content_type": "post_text",
            "title": "Scheduled media",
            "body": "A scheduled photo with validated local media.",
            "hashtags": ["#Media"],
            "media_asset_id": asset_id,
        },
    )
    assert created.status_code == 201
    draft = created.json()
    assert client.post(f"/content/drafts/{draft['draft_id']}/approve").status_code == 200
    scheduled = client.post(
        f"/content/drafts/{draft['draft_id']}/schedule",
        json={"scheduled_at": (datetime.now(UTC) + timedelta(days=1)).isoformat()},
    )
    assert scheduled.status_code == 201
    schedule = scheduled.json()

    tasks = TaskRepository(get_settings().database_path)
    with tasks._connection() as connection:
        connection.execute(
            "UPDATE content_publish_schedules SET scheduled_at = ? WHERE schedule_id = ?",
            ((datetime.now(UTC) - timedelta(seconds=1)).isoformat(), schedule["schedule_id"]),
        )

    adapter = CapturingMediaAdapter()
    dispatcher = ContentScheduleDispatcher(
        get_settings().database_path,
        adapters={"telegram": adapter},
    )
    result = dispatcher.run_once()

    assert result == {"schedule_id": schedule["schedule_id"], "status": "published"}
    assert adapter.draft is not None
    assert adapter.draft["media_asset_id"] == asset_id
    media = adapter.draft["media_asset"]
    assert media["filename"] == "dispatch.png"
    assert media["file_size"] == len(b"\x89PNG\r\n\x1a\nmedia-dispatch-fixture")



def test_dispatch_fails_closed_if_attached_media_disappears():
    client = authenticated_client()
    upload = client.post(
        "/content/assets",
        content=b"\x89PNG\r\n\x1a\nmissing-media-fixture",
        headers={"Content-Type": "image/png", "X-File-Name": "missing.png"},
    )
    assert upload.status_code == 201
    asset_id = upload.json()["asset_id"]

    created = client.post(
        "/content/drafts",
        json={
            "platform": "telegram",
            "content_type": "post_text",
            "title": "Missing media",
            "body": "The missing asset must not be published.",
            "media_asset_id": asset_id,
        },
    )
    assert created.status_code == 201
    draft = created.json()
    assert client.post(f"/content/drafts/{draft['draft_id']}/approve").status_code == 200
    scheduled = client.post(
        f"/content/drafts/{draft['draft_id']}/schedule",
        json={"scheduled_at": (datetime.now(UTC) + timedelta(days=1)).isoformat()},
    )
    assert scheduled.status_code == 201
    schedule = scheduled.json()

    settings = get_settings()
    media_repository = MediaAssetRepository(settings.database_path)
    asset = media_repository.get("local-owner", UUID(asset_id))
    assert asset is not None
    media_repository.file_path(str(asset["storage_key"])).unlink()

    tasks = TaskRepository(settings.database_path)
    with tasks._connection() as connection:
        connection.execute(
            "UPDATE content_publish_schedules SET scheduled_at = ? WHERE schedule_id = ?",
            ((datetime.now(UTC) - timedelta(seconds=1)).isoformat(), schedule["schedule_id"]),
        )

    adapter = CapturingMediaAdapter()
    dispatcher = ContentScheduleDispatcher(settings.database_path, adapters={"telegram": adapter})
    result = dispatcher.run_once()

    assert result == {
        "schedule_id": schedule["schedule_id"],
        "status": "failed",
        "reason_code": "media_asset_unavailable",
    }
    assert adapter.draft is None
