"""Explicitly configured social publishing adapters."""
from __future__ import annotations

from pathlib import Path
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

        media = draft.get("media_asset")
        if media is None:
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
        else:
            if not isinstance(media, dict):
                raise PermanentPublishError("Telegram media metadata is invalid")
            media_type = str(media.get("media_type", ""))
            upload_field = {
                "image/jpeg": "photo",
                "image/png": "photo",
                "video/mp4": "video",
            }.get(media_type)
            media_path = Path(str(media.get("path", "")))
            filename = Path(str(media.get("filename", ""))).name
            try:
                file_size = media_path.stat().st_size
            except OSError as exc:
                raise PermanentPublishError("Telegram media file is unavailable") from exc
            if (
                upload_field is None
                or not filename
                or not media_path.is_file()
                or not 1 <= file_size <= 25_000_000
                or file_size != int(media.get("file_size", -1))
            ):
                raise PermanentPublishError("Telegram media file is invalid or exceeds the upload limit")
            if len(text) > 1024:
                raise PermanentPublishError("Telegram media caption exceeds the 1024 character limit")
            endpoint = f"https://api.telegram.org/bot{self._bot_token}/sendPhoto" if upload_field == "photo" else f"https://api.telegram.org/bot{self._bot_token}/sendVideo"
            try:
                with media_path.open("rb") as media_file:
                    response = self._client.post(
                        endpoint,
                        data={"chat_id": self._chat_id, "caption": text},
                        files={upload_field: (filename, media_file, media_type)},
                    )
            except OSError as exc:
                raise PermanentPublishError("Telegram media file is unavailable") from exc
            except httpx.HTTPError as exc:
                # The provider may have accepted the upload before the response was lost.
                raise UnknownPublishOutcome("Telegram media request outcome is unknown") from exc

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
