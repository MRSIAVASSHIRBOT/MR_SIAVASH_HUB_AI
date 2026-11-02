"""Authenticated local-first content draft lifecycle; no publishing side effects."""
from __future__ import annotations

import sqlite3
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field, field_validator

from mrhub.api.dependencies import require_user
from mrhub.config import get_settings
from mrhub.content.repository import ContentDraftRepository
from mrhub.security.audit import AuditLogger
from mrhub.security.auth import AuthenticatedUser

router = APIRouter(prefix="/content/drafts", tags=["content"], dependencies=[Depends(require_user)])
Platform = Literal["instagram", "telegram", "generic"]
ContentType = Literal["caption", "script", "reel_script", "post_text", "video_brief"]
DraftStatus = Literal["draft", "approved", "archived"]


class ContentDraftCreate(BaseModel):
    platform: Platform
    content_type: ContentType
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=20_000)
    hashtags: list[str] = Field(default_factory=list, max_length=30)

    @field_validator("title")
    @classmethod
    def title_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Draft title must not be blank")
        return value.strip()

    @field_validator("body")
    @classmethod
    def body_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Draft body must not be blank")
        return value.strip()

    @field_validator("hashtags")
    @classmethod
    def normalize_hashtags(cls, values: list[str]) -> list[str]:
        normalized = [value.strip() for value in values]
        if any(not value or len(value) > 60 for value in normalized):
            raise ValueError("Each hashtag must contain 1 to 60 characters")
        return normalized


class ContentDraftUpdate(BaseModel):
    platform: Platform | None = None
    content_type: ContentType | None = None
    title: str | None = Field(default=None, min_length=1, max_length=200)
    body: str | None = Field(default=None, min_length=1, max_length=20_000)
    hashtags: list[str] | None = Field(default=None, max_length=30)

    @field_validator("title")
    @classmethod
    def title_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("Draft title must not be blank")
        return value.strip() if value is not None else None

    @field_validator("body")
    @classmethod
    def body_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("Draft body must not be blank")
        return value.strip() if value is not None else None

    @field_validator("hashtags")
    @classmethod
    def normalize_hashtags(cls, values: list[str] | None) -> list[str] | None:
        if values is None:
            return None
        normalized = [value.strip() for value in values]
        if any(not value or len(value) > 60 for value in normalized):
            raise ValueError("Each hashtag must contain 1 to 60 characters")
        return normalized


def _repository() -> ContentDraftRepository:
    return ContentDraftRepository(get_settings().database_path)


def _audit(
    repository: ContentDraftRepository,
    user: AuthenticatedUser,
    event: str,
    draft_id: str,
    reason: str,
) -> None:
    AuditLogger(repository.tasks).record(
        event_type=event,
        outcome="success",
        subject_type="content_draft",
        subject_id=draft_id,
        actor_type="user",
        actor_id=user.user_id,
        metadata={"reason_code": reason},
    )


def _duplicate_conflict() -> HTTPException:
    return HTTPException(
        status_code=409,
        detail="An identical draft already exists for this owner and platform/content type",
    )


@router.post("", status_code=201)
def create_draft(
    payload: ContentDraftCreate,
    user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> dict[str, object]:
    repository = _repository()
    try:
        record = repository.create(user.user_id, user.user_id, **payload.model_dump())
    except sqlite3.IntegrityError as exc:
        duplicate = repository.find_duplicate(
            user.user_id,
            repository._hash(
                payload.platform, payload.content_type, payload.body, payload.hashtags
            ),
        )
        if duplicate is not None:
            raise _duplicate_conflict() from exc
        raise HTTPException(status_code=422, detail="Content draft violates a storage constraint") from exc
    _audit(repository, user, "content.draft_created", str(record["draft_id"]), "draft_created")
    return record


@router.get("")
def list_drafts(
    user: Annotated[AuthenticatedUser, Depends(require_user)],
    limit: int = Query(default=50, ge=1, le=100),
    status: DraftStatus | None = None,
) -> dict[str, object]:
    records = _repository().list_drafts(user.user_id, limit, status)
    return {"drafts": records, "count": len(records)}


@router.get("/{draft_id}/versions")
def list_draft_versions(
    draft_id: UUID,
    user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> dict[str, object]:
    versions = _repository().versions(user.user_id, draft_id)
    if versions is None:
        raise HTTPException(status_code=404, detail="Content draft not found")
    return {"versions": versions, "count": len(versions)}


@router.get("/{draft_id}")
def get_draft(
    draft_id: UUID,
    user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> dict[str, object]:
    record = _repository().get(user.user_id, draft_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Content draft not found")
    return record


@router.patch("/{draft_id}")
def update_draft(
    draft_id: UUID,
    payload: ContentDraftUpdate,
    user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> dict[str, object]:
    submitted = payload.model_dump(exclude_unset=True)
    if not submitted or any(value is None for value in submitted.values()):
        raise HTTPException(status_code=422, detail="Provide at least one non-null field")
    repository = _repository()
    try:
        record = repository.update(user.user_id, user.user_id, draft_id, submitted)
    except sqlite3.IntegrityError as exc:
        raise _duplicate_conflict() from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if record is None:
        raise HTTPException(status_code=404, detail="Content draft not found")
    _audit(repository, user, "content.draft_updated", str(draft_id), "draft_updated")
    return record


@router.post("/{draft_id}/approve")
def approve_draft(
    draft_id: UUID,
    user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> dict[str, object]:
    repository = _repository()
    try:
        record = repository.approve(user.user_id, draft_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if record is None:
        raise HTTPException(status_code=404, detail="Content draft not found")
    _audit(repository, user, "content.draft_approved", str(draft_id), "draft_approved")
    return record


@router.post("/{draft_id}/revoke-approval")
def revoke_draft_approval(
    draft_id: UUID,
    user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> dict[str, object]:
    repository = _repository()
    try:
        record = repository.revoke_approval(user.user_id, draft_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if record is None:
        raise HTTPException(status_code=404, detail="Content draft not found")
    _audit(repository, user, "content.draft_approval_revoked", str(draft_id), "approval_revoked")
    return record


@router.post("/{draft_id}/archive")
def archive_draft(
    draft_id: UUID,
    user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> dict[str, object]:
    repository = _repository()
    record = repository.archive(user.user_id, draft_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Content draft not found")
    _audit(repository, user, "content.draft_archived", str(draft_id), "draft_archived")
    return record


@router.post("/{draft_id}/restore")
def restore_draft(
    draft_id: UUID,
    user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> dict[str, object]:
    repository = _repository()
    try:
        record = repository.restore(user.user_id, draft_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if record is None:
        raise HTTPException(status_code=404, detail="Content draft not found")
    _audit(repository, user, "content.draft_restored", str(draft_id), "draft_restored")
    return record


@router.delete("/{draft_id}", status_code=204)
def delete_draft(
    draft_id: UUID,
    user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> Response:
    repository = _repository()
    if not repository.delete(user.user_id, draft_id):
        raise HTTPException(status_code=404, detail="Content draft not found")
    _audit(repository, user, "content.draft_deleted", str(draft_id), "draft_deleted")
    return Response(status_code=204)
