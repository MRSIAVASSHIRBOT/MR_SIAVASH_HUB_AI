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
