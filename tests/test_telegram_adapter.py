import httpx
import pytest
from pydantic import SecretStr

from mrhub.config import Settings
from mrhub.content.dispatcher import (
    PermanentPublishError,
    TransientPublishError,
    UnknownPublishOutcome,
)
from mrhub.content.providers import TelegramBotApiAdapter, configured_publish_adapters


def _draft() -> dict[str, object]:
    return {
        "platform": "telegram",
        "body": "DNS troubleshooting basics",
        "hashtags": ["#DNS", "#Networking"],
    }


def test_telegram_adapter_posts_text_and_returns_provider_message_id() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 987}})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    adapter = TelegramBotApiAdapter("test-secret-token", "@test_channel", client=client)

    receipt = adapter.publish(_draft(), idempotency_key="test-key")

    assert receipt.provider_post_id == "987"
    assert len(requests) == 1
    assert requests[0].url.path.endswith("/sendMessage")
    payload = __import__("json").loads(requests[0].content)
    assert payload["chat_id"] == "@test_channel"
    assert payload["text"] == "DNS troubleshooting basics\n\n#DNS #Networking"
    client.close()


def test_telegram_adapter_classifies_rate_limit_as_safe_transient_rejection() -> None:
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(429, json={"ok": False, "error_code": 429})
        )
    )
    adapter = TelegramBotApiAdapter("test-token", "test-chat", client=client)
    with pytest.raises(TransientPublishError):
        adapter.publish(_draft(), idempotency_key="test-key")
    client.close()


def test_telegram_adapter_classifies_permanent_rejection_without_retry() -> None:
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(400, json={"ok": False, "error_code": 400})
        )
    )
    adapter = TelegramBotApiAdapter("test-token", "test-chat", client=client)
    with pytest.raises(PermanentPublishError):
        adapter.publish(_draft(), idempotency_key="test-key")
    client.close()


def test_telegram_transport_failure_is_ambiguous_and_must_not_be_retried_blindly() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("test timeout", request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    adapter = TelegramBotApiAdapter("test-token", "test-chat", client=client)
    with pytest.raises(UnknownPublishOutcome):
        adapter.publish(_draft(), idempotency_key="test-key")
    client.close()


def test_provider_is_created_only_when_both_telegram_settings_exist() -> None:
    missing = Settings(telegram_bot_token=None, telegram_chat_id="@channel")
    assert configured_publish_adapters(missing) == {}

    configured = Settings(
        telegram_bot_token=SecretStr("test-token"),
        telegram_chat_id="@channel",
    )
    adapters = configured_publish_adapters(configured)
    assert set(adapters) == {"telegram"}
    adapters["telegram"].close()


@pytest.mark.parametrize(
    ("media_type", "field", "endpoint", "filename"),
    [
        ("image/png", "photo", "/sendPhoto", "preview.png"),
        ("video/mp4", "video", "/sendVideo", "clip.mp4"),
    ],
)
def test_telegram_adapter_uploads_media_as_multipart(
    tmp_path, media_type, field, endpoint, filename
):
    media_path = tmp_path / filename
    media_path.write_bytes(b"bounded-test-media")
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 654}})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    adapter = TelegramBotApiAdapter("test-token", "@test_channel", client=client)
    draft = {
        **_draft(),
        "body": "A media post",
        "hashtags": ["#Media"],
        "media_asset": {
            "media_type": media_type,
            "filename": filename,
            "path": str(media_path),
            "file_size": media_path.stat().st_size,
        },
    }

    receipt = adapter.publish(draft, idempotency_key="media-test-key")

    assert receipt.provider_post_id == "654"
    assert len(requests) == 1
    assert requests[0].url.path.endswith(endpoint)
    assert "multipart/form-data" in requests[0].headers["content-type"]
    assert f'name="{field}"'.encode() in requests[0].content
    assert b'name="caption"' in requests[0].content
    assert b"A media post" in requests[0].content
    client.close()


def test_telegram_adapter_rejects_oversized_media_caption_before_network(tmp_path):
    media_path = tmp_path / "preview.png"
    media_path.write_bytes(b"media")
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"ok": True, "result": {"message_id": 1}})
        )
    )
    adapter = TelegramBotApiAdapter("test-token", "@test_channel", client=client)
    draft = {
        **_draft(),
        "body": "x" * 1025,
        "hashtags": [],
        "media_asset": {
            "media_type": "image/png",
            "filename": "preview.png",
            "path": str(media_path),
            "file_size": media_path.stat().st_size,
        },
    }

    with pytest.raises(PermanentPublishError):
        adapter.publish(draft, idempotency_key="media-caption-limit")
    client.close()
