"""Explicitly configured social publishing adapters."""
from __future__ import annotations

from typing import Any

import httpx

from mrhub.config import Settings, get_settings
from mrhub.content.dispatcher import (
    PermanentPublishError,
    PublishReceipt,
    TransientPublishError,
    UnknownPublishOutcome,
)


class TelegramBotApiAdapter:
    """Publish text posts to a Telegram chat/channel using the Bot API.

    Telegram does not offer an idempotency key for sendMessage. The key is accepted
    by the adapter contract but cannot be used to guarantee exactly-once delivery.
    """

    def __init__(
        self,
        bot_token: str,
        chat_id: str,
        *,
        client: httpx.Client | None = None,
    ) -> None:
        if not bot_token.strip() or not chat_id.strip():
            raise ValueError("Telegram bot token and chat ID are required")
        self._bot_token = bot_token
        self._chat_id = chat_id
        self._client = client or httpx.Client(timeout=15.0)
        self._owns_client = client is None

    def publish(
        self, draft: dict[str, object], *, idempotency_key: str
    ) -> PublishReceipt:
        del idempotency_key  # Telegram sendMessage has no provider-side idempotency support.
        if draft.get("platform") != "telegram":
            raise PermanentPublishError("Telegram adapter received a non-Telegram draft")
        body = str(draft.get("body", "")).strip()
        hashtags = draft.get("hashtags", [])
        if isinstance(hashtags, list):
            suffix = " ".join(str(tag).strip() for tag in hashtags if str(tag).strip())
        else:
            suffix = ""
        text = "\n\n".join(part for part in (body, suffix) if part)
        if not text:
            raise PermanentPublishError("Telegram message is empty")
        if len(text) > 4096:
            raise PermanentPublishError("Telegram message exceeds the text limit")

        endpoint = f"https://api.telegram.org/bot{self._bot_token}/sendMessage"
        try:
            response = self._client.post(
                endpoint,
                json={"chat_id": self._chat_id, "text": text},
            )
        except httpx.HTTPError as exc:
            # A transport failure can occur after Telegram has accepted the message.
            raise UnknownPublishOutcome("Telegram request outcome is unknown") from exc

        if response.status_code == 429:
            raise TransientPublishError("Telegram rate limited the request")
        if 400 <= response.status_code < 500:
            raise PermanentPublishError("Telegram rejected the request")
        if response.status_code >= 500:
            raise UnknownPublishOutcome("Telegram server response is ambiguous")

        try:
            payload: Any = response.json()
        except ValueError as exc:
            raise UnknownPublishOutcome("Telegram returned an unreadable response") from exc
        if not isinstance(payload, dict):
            raise UnknownPublishOutcome("Telegram returned an unexpected response")
        if payload.get("ok") is not True:
            error_code = payload.get("error_code")
            if error_code == 429:
                raise TransientPublishError("Telegram rate limited the request")
            raise PermanentPublishError("Telegram rejected the request")
        result = payload.get("result")
        if not isinstance(result, dict) or result.get("message_id") is None:
            raise UnknownPublishOutcome("Telegram confirmation omitted the message ID")
        return PublishReceipt(provider_post_id=str(result["message_id"]))

    def close(self) -> None:
        if self._owns_client:
            self._client.close()


def configured_publish_adapters(settings: Settings | None = None) -> dict[str, TelegramBotApiAdapter]:
    """Return only adapters whose credentials are explicitly configured."""
    config = settings or get_settings()
    if config.telegram_bot_token is None or not config.telegram_chat_id:
        return {}
    return {
        "telegram": TelegramBotApiAdapter(
            config.telegram_bot_token.get_secret_value(),
            config.telegram_chat_id,
        )
    }
