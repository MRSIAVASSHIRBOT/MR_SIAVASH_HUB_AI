from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

from client_helpers import authenticated_client
from mrhub.config import get_settings
from mrhub.content.dispatcher import (
    ContentScheduleDispatcher,
    PermanentPublishError,
    PublishReceipt,
    TransientPublishError,
    UnknownPublishOutcome,
)
from mrhub.content.instagram_reels import InstagramGraphPublishingAdapter
from mrhub.media.repository import MediaAssetRepository


def make_adapter(handler):
    client = httpx.Client(transport=httpx.MockTransport(handler))
    adapter = InstagramGraphPublishingAdapter(
        "test-token-never-log",
        "17841400000000000",
        "v24.0",
        client=client,
    )
    return adapter, client


def test_reels_adapter_creates_container_checks_readiness_then_publishes():
    requests = []

    def handler(request):
        requests.append(request)
        if request.method == "GET":
            return httpx.Response(200, json={"status_code": "FINISHED"})
        if request.url.path.endswith("/media"):
            return httpx.Response(200, json={"id": "reel-container-123"})
        return httpx.Response(200, json={"id": "reel-post-456"})

    adapter, client = make_adapter(handler)
    try:
        receipt = adapter.publish(
            {
                "platform": "instagram",
                "content_type": "reel",
                "media_type": "video/mp4",
                "media_url": "https://media.example-cdn.com/reel.mp4",
                "body": "A useful educational Reel",
                "hashtags": ["#AI", "#Learning"],
            },
            idempotency_key="approved-reel-v1",
        )
    finally:
        client.close()

    assert receipt.provider_post_id == "reel-post-456"
    assert [request.method for request in requests] == ["POST", "GET", "POST"]
    create_form = parse_qs(requests[0].content.decode())
    assert create_form["media_type"] == ["REELS"]
    assert create_form["video_url"] == ["https://media.example-cdn.com/reel.mp4"]
    assert create_form["share_to_feed"] == ["true"]
    assert create_form["caption"] == ["A useful educational Reel\n\n#AI #Learning"]
    assert requests[1].url.path.endswith("/reel-container-123")
    assert "status_code,status" in requests[1].url.query.decode()
    publish_form = parse_qs(requests[2].content.decode())
    assert publish_form["creation_id"] == ["reel-container-123"]


def test_reels_adapter_does_not_publish_while_container_is_processing():
    requests = []

    def handler(request):
        requests.append(request)
        if request.method == "GET":
            return httpx.Response(200, json={"status_code": "IN_PROGRESS"})
        return httpx.Response(200, json={"id": "reel-container-123"})

    adapter, client = make_adapter(handler)
    try:
        with pytest.raises(TransientPublishError):
            adapter.publish(
                {
                    "platform": "instagram",
                    "content_type": "reel",
                    "media_type": "video/mp4",
                    "media_url": "https://media.example-cdn.com/reel.mp4",
                    "body": "Caption",
                },
                idempotency_key="key",
            )
    finally:
        client.close()

    assert [request.method for request in requests] == ["POST", "GET"]


def test_reels_adapter_rejects_non_mp4_before_provider_request():
    requests = []
    adapter, client = make_adapter(
        lambda request: requests.append(request) or httpx.Response(200, json={"id": "x"})
    )
    try:
        with pytest.raises(PermanentPublishError):
            adapter.publish(
                {
                    "platform": "instagram",
                    "content_type": "reel",
                    "media_type": "image/png",
                    "media_url": "https://media.example-cdn.com/image.png",
                    "body": "Caption",
                },
                idempotency_key="key",
            )
    finally:
        client.close()
    assert requests == []


def test_reels_adapter_quarantines_already_published_container():
    adapter, client = make_adapter(
        lambda request: httpx.Response(200, json={"status_code": "PUBLISHED"})
        if request.method == "GET"
        else httpx.Response(200, json={"id": "container-123"})
    )
    try:
        with pytest.raises(UnknownPublishOutcome):
            adapter.publish(
                {
                    "platform": "instagram",
                    "content_type": "reel",
                    "media_type": "video/mp4",
                    "media_url": "https://media.example-cdn.com/reel.mp4",
                    "body": "Caption",
                },
                idempotency_key="key",
            )
    finally:
        client.close()


def test_dispatcher_delivers_only_processed_mp4_as_signed_reel_media(monkeypatch):
    monkeypatch.setenv("MRH_PUBLIC_MEDIA_BASE_URL", "https://media.example.com")
    monkeypatch.setenv(
        "MRH_PUBLIC_MEDIA_SIGNING_KEY",
        "test-only-signing-key-0123456789abcdef",
    )
    get_settings.cache_clear()
    client = authenticated_client()
    video_bytes = b"\x00\x00\x00\x18ftypisom" + b"reel-video-fixture"
    uploaded = client.post(
        "/content/assets",
        content=video_bytes,
        headers={"Content-Type": "video/mp4", "X-File-Name": "approved-reel.mp4"},
    )
    assert uploaded.status_code == 201
    asset_id = uploaded.json()["asset_id"]
    owner_id = uploaded.json()["owner_user_id"]
    repository = MediaAssetRepository(get_settings().database_path)
    with repository.tasks._connection() as connection:
        connection.execute(
            "UPDATE content_assets SET processing_status = 'processed', "
            "processing_profile = 'video_render_cut_v1' WHERE asset_id = ? AND owner_user_id = ?",
            (asset_id, owner_id),
        )

    created = client.post(
        "/content/drafts",
        json={
            "platform": "instagram",
            "content_type": "reel",
            "title": "Approved Reel fixture",
            "body": "An educational short video.",
            "hashtags": ["#Education"],
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
    with repository.tasks._connection() as connection:
        connection.execute(
            "UPDATE content_publish_schedules SET scheduled_at = ? WHERE schedule_id = ?",
            ((datetime.now(UTC) - timedelta(seconds=1)).isoformat(), schedule["schedule_id"]),
        )

    class InspectingAdapter:
        def __init__(self):
            self.draft = None

        def publish(self, draft, *, idempotency_key):
            self.draft = draft
            assert idempotency_key
            return PublishReceipt(provider_post_id="instagram-reel-789")

    adapter = InspectingAdapter()
    dispatcher = ContentScheduleDispatcher(
        get_settings().database_path,
        adapters={"instagram": adapter},
    )
    result = dispatcher.run_once()

    assert result == {"schedule_id": schedule["schedule_id"], "status": "published"}
    assert adapter.draft is not None
    assert adapter.draft["content_type"] == "reel"
    assert adapter.draft["media_type"] == "video/mp4"
    media_url = str(adapter.draft["media_url"])
    parsed = urlsplit(media_url)
    response = client.get(f"{parsed.path}?{parsed.query}")
    assert response.status_code == 200
    assert response.headers["content-type"] == "video/mp4"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.content == video_bytes
    get_settings.cache_clear()
