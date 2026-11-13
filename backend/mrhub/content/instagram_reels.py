"""Instagram Reels publishing over the official Graph API."""

from __future__ import annotations

from typing import Any

import httpx

from mrhub.content.dispatcher import (
    PermanentPublishError,
    PublishReceipt,
    TransientPublishError,
    UnknownPublishOutcome,
)
from mrhub.content.providers import InstagramGraphImageAdapter


class InstagramGraphPublishingAdapter(InstagramGraphImageAdapter):
    """Publish approved images and Reels; Reels use a confirmed container state."""

    def _get_container_status(self, container_id: str) -> str:
        try:
            response = self._client.get(
                f"{self._base_url}/{container_id}",
                params={"fields": "status_code,status"},
                headers={"Authorization": f"Bearer {self._access_token}"},
            )
        except httpx.HTTPError as exc:
            # No publish request has been made yet, so this read can be retried safely.
            raise TransientPublishError(
                "Instagram Reel container status could not be checked"
            ) from exc
        if response.status_code == 429:
            raise TransientPublishError("Instagram Graph API rate limited the request")
        if response.status_code >= 500:
            raise TransientPublishError(
                "Instagram Graph API temporarily could not report Reel readiness"
            )
        if response.status_code >= 400:
            raise PermanentPublishError(
                "Instagram Graph API rejected the Reel status request"
            )
        try:
            payload: Any = response.json()
        except ValueError as exc:
            raise TransientPublishError(
                "Instagram Graph API returned an unreadable Reel status"
            ) from exc
        if not isinstance(payload, dict) or payload.get("error"):
            raise PermanentPublishError(
                "Instagram Graph API rejected the Reel status request"
            )
        status = payload.get("status_code")
        if not isinstance(status, str):
            raise UnknownPublishOutcome(
                "Instagram Reel container status was not confirmed"
            )
        return status.upper()

    def publish(
        self, draft: dict[str, object], *, idempotency_key: str
    ) -> PublishReceipt:
        if draft.get("content_type") != "reel":
            return super().publish(draft, idempotency_key=idempotency_key)

        del idempotency_key
        if draft.get("platform") != "instagram":
            raise PermanentPublishError(
                "Instagram adapter received a non-Instagram draft"
            )
        if draft.get("media_type") != "video/mp4":
            raise PermanentPublishError(
                "Instagram Reels require an approved MP4 video asset"
            )
        media_url = self._validate_public_media_url(draft.get("media_url"))
        body = str(draft.get("body", "")).strip()
        hashtags = draft.get("hashtags", [])
        suffix = (
            " ".join(str(tag).strip() for tag in hashtags if str(tag).strip())
            if isinstance(hashtags, list)
            else ""
        )
        caption = "\n\n".join(part for part in (body, suffix) if part)
        if not caption or len(caption) > 2_200:
            raise PermanentPublishError(
                "Instagram caption must contain 1 to 2200 characters"
            )

        container = self._post(
            f"{self._user_id}/media",
            {
                "media_type": "REELS",
                "video_url": media_url,
                "caption": caption,
                "share_to_feed": "true",
            },
        )
        container_id = container.get("id")
        if not isinstance(container_id, (str, int)) or not str(container_id):
            raise UnknownPublishOutcome(
                "Instagram did not confirm Reel container creation"
            )

        status = self._get_container_status(str(container_id))
        if status == "IN_PROGRESS":
            raise TransientPublishError(
                "Instagram is still processing the Reel container"
            )
        if status in {"ERROR", "EXPIRED"}:
            raise PermanentPublishError(
                "Instagram could not prepare the Reel container"
            )
        if status == "PUBLISHED":
            raise UnknownPublishOutcome(
                "Instagram reports the Reel container was already published"
            )
        if status != "FINISHED":
            raise UnknownPublishOutcome(
                "Instagram Reel container readiness is ambiguous"
            )

        published = self._post(
            f"{self._user_id}/media_publish",
            {"creation_id": str(container_id)},
        )
        post_id = published.get("id")
        if not isinstance(post_id, (str, int)) or not str(post_id):
            raise UnknownPublishOutcome(
                "Instagram did not confirm Reel publication"
            )
        return PublishReceipt(provider_post_id=str(post_id))
