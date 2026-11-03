"""Authenticated prompt composition endpoint for video production workflows."""
from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from mrhub.api.dependencies import require_user
from mrhub.security.auth import AuthenticatedUser
from mrhub.video_intelligence.service import build_generation_prompt

router = APIRouter(
    prefix="/video-intelligence",
    tags=["video-intelligence"],
    dependencies=[Depends(require_user)],
)


class PromptCompositionRequest(BaseModel):
    style_summary: str = Field(min_length=1, max_length=1000)
    beats: list[dict[str, Any]] = Field(default_factory=list, max_length=20)
    duration_seconds: int = Field(default=10, ge=3, le=60)
    aspect_ratio: str = Field(default="9:16", pattern=r"^(9:16|16:9|1:1|4:5)$")
    brand_name: str | None = Field(default=None, max_length=80)
    colors: list[str] = Field(default_factory=list, max_length=8)
    typography: str | None = Field(default=None, max_length=240)
    sound_design: str | None = Field(default=None, max_length=500)
    final_frame: str | None = Field(default=None, max_length=500)


@router.post("/prompts/compose")
def compose_prompt(
    payload: PromptCompositionRequest,
    _user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> dict[str, str]:
    """Compose a provider-neutral prompt from reviewed analysis facts."""
    prompt = build_generation_prompt(**payload.model_dump())
    return {"prompt": prompt, "status": "composed", "execution": "not_started"}
