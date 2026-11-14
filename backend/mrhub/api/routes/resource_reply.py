"""Authenticated owner-scoped configuration and preview for resource replies."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from mrhub.api.dependencies import require_user
from mrhub.config import get_settings
from mrhub.content.resource_reply import (
    build_optional_support_resource_reply,
    validate_resource_url,
)
from mrhub.content.resource_reply_config import ResourceReplyConfigRepository
from mrhub.security.auth import AuthenticatedUser

router = APIRouter(
    prefix="/content/resource-reply",
    tags=["content-resource-reply"],
    dependencies=[Depends(require_user)],
)


class ResourceReplyConfig(BaseModel):
    keyword: str = Field(default="راهنما", min_length=1, max_length=80)
    resource_url: str = Field(default="", max_length=2048)
    resource_label: str = Field(default="محتوای آموزشی", min_length=1, max_length=120)
    intro_text: str = Field(default="سلام! ✨", max_length=500)
    include_follow: bool = True
    follow_cta_text: str = Field(
        default="اگر این آموزش برات مفیده، خوشحال می‌شیم صفحه‌مون رو دنبال کنی. 💚",
        max_length=300,
    )
    include_share: bool = True
    share_cta_text: str = Field(
        default="این پست رو هم برای دوستانت بفرست تا افراد بیشتری از آموزش رایگان استفاده کنن. 📢",
        max_length=300,
    )


def _repository() -> ResourceReplyConfigRepository:
    return ResourceReplyConfigRepository(get_settings().database_path)


def _normalized(payload: ResourceReplyConfig, *, require_url: bool) -> dict[str, object]:
    values = payload.model_dump()
    for field in (
        "keyword", "resource_url", "resource_label", "intro_text",
        "follow_cta_text", "share_cta_text",
    ):
        values[field] = str(values[field]).strip()
    if any(character in values["keyword"] for character in "\r\n\x00"):
        raise HTTPException(status_code=422, detail="Keyword must be a single line")
    if not values["keyword"]:
        raise HTTPException(status_code=422, detail="Keyword is required")
    if not values["resource_label"] or any(
        character in values["resource_label"] for character in "\r\n\x00"
    ):
        raise HTTPException(status_code=422, detail="Resource label must be a single line")
    for field in ("intro_text", "follow_cta_text", "share_cta_text"):
        if "\x00" in values[field]:
            raise HTTPException(status_code=422, detail="Reply text contains an invalid character")
    if values["include_follow"] and not values["follow_cta_text"]:
        raise HTTPException(status_code=422, detail="Follow text is required when enabled")
    if values["include_share"] and not values["share_cta_text"]:
        raise HTTPException(status_code=422, detail="Share text is required when enabled")
    if require_url and not values["resource_url"]:
        raise HTTPException(status_code=422, detail="A public HTTPS resource URL is required for preview")
    if values["resource_url"]:
        try:
            values["resource_url"] = validate_resource_url(values["resource_url"])
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    return values


@router.get("/config", summary="Read the current user's resource reply settings")
def get_resource_reply_config(
    user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> dict[str, object]:
    return _repository().get(user.user_id)


@router.put("/config", summary="Save customizable keyword and resource reply fields")
def save_resource_reply_config(
    payload: ResourceReplyConfig,
    user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> dict[str, object]:
    values = _normalized(payload, require_url=False)
    return _repository().save(user.user_id, values)


@router.post("/preview", summary="Preview a reply using user-supplied configuration")
def preview_resource_reply(
    payload: ResourceReplyConfig,
    _user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> dict[str, object]:
    values = _normalized(payload, require_url=True)
    reply = build_optional_support_resource_reply(
        str(values["resource_url"]),
        resource_label=str(values["resource_label"]),
        intro_text=str(values["intro_text"]),
        include_follow=bool(values["include_follow"]),
        follow_cta_text=str(values["follow_cta_text"]),
        include_share=bool(values["include_share"]),
        share_cta_text=str(values["share_cta_text"]),
    )
    return {
        "keyword": values["keyword"],
        "reply": reply,
        "resource_delivery_unconditional": True,
        "automation_active": False,
    }
