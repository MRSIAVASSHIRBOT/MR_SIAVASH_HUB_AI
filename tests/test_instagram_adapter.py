from urllib.parse import parse_qs

import httpx
import pytest

from mrhub.content.dispatcher import (
    PermanentPublishError,
    TransientPublishError,
    UnknownPublishOutcome,
)
from mrhub.content.providers import InstagramGraphImageAdapter


def make_adapter(handler):
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return InstagramGraphImageAdapter(
        "test-token-never-log",
        "17841400000000000",
        "v24.0",
        client=client,
    ), client


def test_instagram_image_publish_uses_container_then_publish_and_returns_id():
    requests = []

    def handler(request):
        requests.append(request)
        if request.url.path.endswith("/media"):
            return httpx.Response(200, json={"id": "container-123"})
        return httpx.Response(200, json={"id": "published-456"})

    adapter, client = make_adapter(handler)
    try:
        receipt = adapter.publish(
            {
                "platform": "instagram",
                "body": "A useful caption",
                "hashtags": ["#AI", "#Security"],
                "media_url": "https://media.example-cdn.com/post.jpg",
            },
            idempotency_key="draft-revision-1",
        )
    finally:
        client.close()

    assert receipt.provider_post_id == "published-456"
    assert len(requests) == 2
    assert requests[0].url.path.endswith("/17841400000000000/media")
    assert requests[1].url.path.endswith("/17841400000000000/media_publish")
    first_form = parse_qs(requests[0].content.decode())
    second_form = parse_qs(requests[1].content.decode())
    assert first_form["access_token"] == ["test-token-never-log"]
    assert first_form["caption"] == ["A useful caption\n\n#AI #Security"]
    assert second_form["creation_id"] == ["container-123"]


@pytest.mark.parametrize(
    "media_url",
    [
        "http://media.example.com/image.jpg",
        "https://localhost/image.jpg",
        "https://127.0.0.1/image.jpg",
        "https://192.168.1.10/image.jpg",
        "https://[::1]/image.jpg",
        "https://media.example-cdn.com:8443/image.jpg",
        "https://service.local/image.jpg",
        "https://user:password@media.example.com/image.jpg",
        "https://media.example.com/image.jpg#fragment",
    ],
)
def test_instagram_rejects_non_public_or_unsafe_media_urls_before_request(media_url):
    requests = []
    adapter, client = make_adapter(
        lambda request: requests.append(request) or httpx.Response(200, json={"id": "x"})
    )
    try:
        with pytest.raises(PermanentPublishError):
            adapter.publish(
                {
                    "platform": "instagram",
                    "body": "Caption",
                    "media_url": media_url,
                },
                idempotency_key="draft-revision-2",
            )
    finally:
        client.close()
    assert requests == []


def test_instagram_rejects_wrong_platform_and_empty_caption():
    adapter, client = make_adapter(lambda request: httpx.Response(200, json={"id": "unused"}))
    try:
        with pytest.raises(PermanentPublishError):
            adapter.publish(
                {"platform": "telegram", "body": "Caption"},
                idempotency_key="key",
            )
        with pytest.raises(PermanentPublishError):
            adapter.publish(
                {
                    "platform": "instagram",
                    "body": "   ",
                    "media_url": "https://media.example-cdn.com/post.jpg",
                },
                idempotency_key="key",
            )
    finally:
        client.close()


def test_instagram_classifies_rate_limit_as_transient():
    adapter, client = make_adapter(
        lambda request: httpx.Response(429, json={"error": {"message": "rate limited"}})
    )
    try:
        with pytest.raises(TransientPublishError):
            adapter.publish(
                {
                    "platform": "instagram",
                    "body": "Caption",
                    "media_url": "https://media.example-cdn.com/post.jpg",
                },
                idempotency_key="key",
            )
    finally:
        client.close()


def test_instagram_classifies_server_failure_as_unknown_outcome():
    adapter, client = make_adapter(
        lambda request: httpx.Response(503, json={"error": {"message": "temporary"}})
    )
    try:
        with pytest.raises(UnknownPublishOutcome):
            adapter.publish(
                {
                    "platform": "instagram",
                    "body": "Caption",
                    "media_url": "https://media.example-cdn.com/post.jpg",
                },
                idempotency_key="key",
            )
    finally:
        client.close()


def test_instagram_missing_container_id_is_unknown_outcome():
    adapter, client = make_adapter(lambda request: httpx.Response(200, json={"ok": True}))
    try:
        with pytest.raises(UnknownPublishOutcome):
            adapter.publish(
                {
                    "platform": "instagram",
                    "body": "Caption",
                    "media_url": "https://media.example-cdn.com/post.jpg",
                },
                idempotency_key="key",
            )
    finally:
        client.close()


def test_instagram_api_error_does_not_echo_provider_payload():
    adapter, client = make_adapter(
        lambda request: httpx.Response(
            400,
            json={"error": {"message": "private diagnostic", "code": 190}},
        )
    )
    try:
        with pytest.raises(PermanentPublishError) as exc:
            adapter.publish(
                {
                    "platform": "instagram",
                    "body": "Caption",
                    "media_url": "https://media.example-cdn.com/post.jpg",
                },
                idempotency_key="key",
            )
    finally:
        client.close()
    assert "private diagnostic" not in str(exc.value)
    assert "test-token-never-log" not in str(exc.value)
