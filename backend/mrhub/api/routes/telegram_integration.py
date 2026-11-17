"""Owner pairing and narrowly scoped Telegram integration endpoints."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
import re
import stat
from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from starlette.background import BackgroundTask

from mrhub.api.dependencies import require_user
from mrhub.api.telegram_auth import require_telegram_scope
from mrhub.config import get_settings
from mrhub.domain.tasks import TaskRecord, TaskStatus
from mrhub.infrastructure.database import TaskRepository
from mrhub.integrations.telegram_pairing import (
    TelegramClientIdentity,
    TelegramPairingError,
    TelegramPairingRepository,
)
from mrhub.jobs.engine import InvalidTaskTransition, JobEngine
from mrhub.jobs.idempotency import IdempotencyConflict, IdempotencyError, IdempotencyRepository
from mrhub.jobs.worker import WorkerEngine
from mrhub.media.repository import MAX_OUTPUT_BYTES, MediaAssetRepository
from mrhub.memory.dreaming import MemoryDreamingEngine
from mrhub.memory.repository import MemoryRepository
from mrhub.memory.validation import MemoryValidationEngine
from mrhub.security.audit import AuditLogger
from mrhub.security.auth import AuthenticatedUser
from mrhub.security.policy import ActionRequest, PolicyDecision, PolicyEngine
from mrhub.video_intelligence.generation_jobs import (
    VideoGenerationCancellationConflict,
    VideoGenerationJobRepository,
)
from mrhub.video_intelligence.generation_routing import (
    GenerationRoutePreviewRequest,
    preview_hybrid_route,
)
from mrhub.video_intelligence.jobs import VideoAnalysisJobRepository
from mrhub.video_intelligence.render_jobs import (
    VideoRenderConflict,
    VideoRenderJobRepository,
)
from mrhub.video_intelligence.render_preflight import inspect_video_render_preflight
from mrhub.video_intelligence.render_snapshot import VideoRenderTimelineSnapshot
from mrhub.video_intelligence.render_snapshot_repository import VideoRenderSnapshotConflict
from mrhub.video_intelligence.timeline import VideoTimeline
from mrhub.video_intelligence.timeline_drafts import VideoTimelineDraftRepository

router = APIRouter(prefix="/integrations/telegram", tags=["telegram-integration"])

TelegramScope = Literal[
    "status:read",
    "tasks:read",
    "tasks:result",
    "tasks:create",
    "tasks:cancel",
    "memory:search",
    "memory:write",
    "video:read",
    "video:render",
    "video:cancel",
]
DEFAULT_SCOPES = ["status:read"]
MAX_TELEGRAM_VIDEO_BYTES = 48_000_000


class PairingChallengeRequest(BaseModel):
    telegram_user_id: int = Field(gt=0)
    client_id: UUID
    label: str = Field(min_length=1, max_length=64)
    scopes: list[TelegramScope] = Field(default_factory=lambda: list(DEFAULT_SCOPES), min_length=1, max_length=10)


class ClientScopesUpdateRequest(BaseModel):
    scopes: list[TelegramScope] = Field(min_length=1, max_length=10)


class PairingChallengeResponse(BaseModel):
    pairing_code: str
    client_id: UUID
    expires_at: str
    scopes: list[TelegramScope]


class PairingExchangeRequest(BaseModel):
    pairing_code: str = Field(min_length=32, max_length=128)
    telegram_user_id: int = Field(gt=0)
    client_id: UUID


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=40, max_length=256)
    telegram_user_id: int = Field(gt=0)


class TaskCreateRequest(BaseModel):
    task_type: str = Field(min_length=1, max_length=80, pattern=r"^[a-zA-Z0-9_.-]+$")
    description: str = Field(default="", max_length=500)


class MemorySearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=200)
    limit: int = Field(default=5, ge=1, le=10)


class MemoryDreamPreviewRequest(BaseModel):
    limit: int = Field(default=100, ge=1, le=100)
    similarity_threshold: float = Field(default=0.82, ge=0.75, le=1.0)


class MemoryValidationPreviewRequest(BaseModel):
    limit: int = Field(default=100, ge=1, le=100)
    similarity_threshold: float = Field(default=0.72, ge=0.65, le=1.0)


class TelegramVideoRenderSubmissionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    draft_id: UUID


def _encode_telegram_task_event_cursor(created_at: str, event_id: str) -> str:
    payload = f"{created_at}\n{event_id}".encode()
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def _decode_telegram_task_event_cursor(cursor: str) -> tuple[str, str]:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,512}", cursor):
        raise ValueError("Invalid task event cursor")
    try:
        padding = "=" * (-len(cursor) % 4)
        payload = base64.b64decode(cursor + padding, altchars=b"-_", validate=True).decode("utf-8")
        created_at, event_id = payload.split("\n", 1)
        if not created_at or len(created_at) > 64:
            raise ValueError("Invalid task event cursor")
        datetime.fromisoformat(created_at)
        parsed_event_id = UUID(event_id)
        if str(parsed_event_id) != event_id.lower():
            raise ValueError("Invalid task event cursor")
    except (binascii.Error, UnicodeDecodeError, ValueError):
        raise ValueError("Invalid task event cursor") from None
    return created_at, str(parsed_event_id)


def _encode_telegram_task_cursor(created_at: str, task_id: str) -> str:
    payload = f"{created_at}\n{task_id}".encode()
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def _decode_telegram_task_cursor(cursor: str) -> tuple[str, str]:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,512}", cursor):
        raise ValueError("Invalid task cursor")
    try:
        padding = "=" * (-len(cursor) % 4)
        payload = base64.b64decode(cursor + padding, altchars=b"-_", validate=True).decode("utf-8")
        created_at, task_id = payload.split("\n", 1)
        if not created_at or len(created_at) > 64:
            raise ValueError("Invalid task cursor")
        datetime.fromisoformat(created_at)
        parsed_task_id = UUID(task_id)
        if str(parsed_task_id) != task_id.lower():
            raise ValueError("Invalid task cursor")
    except (binascii.Error, UnicodeDecodeError, ValueError):
        raise ValueError("Invalid task cursor") from None
    return created_at, str(parsed_task_id)


def _encode_telegram_generation_cursor(created_at: str, generation_id: str) -> str:
    payload = f"{created_at}\n{generation_id}".encode()
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def _decode_telegram_generation_cursor(cursor: str) -> tuple[str, UUID]:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,512}", cursor):
        raise ValueError("Invalid generation cursor")
    try:
        padding = "=" * (-len(cursor) % 4)
        payload = base64.b64decode(
            cursor + padding, altchars=b"-_", validate=True
        ).decode("utf-8")
        created_at, raw_generation_id = payload.split("\n", 1)
        if not created_at or len(created_at) > 64:
            raise ValueError("Invalid generation cursor")
        parsed_at = datetime.fromisoformat(created_at)
        if parsed_at.tzinfo is None or parsed_at.utcoffset() is None:
            raise ValueError("Invalid generation cursor")
        generation_id = UUID(raw_generation_id)
        if str(generation_id) != raw_generation_id.lower():
            raise ValueError("Invalid generation cursor")
    except (binascii.Error, UnicodeDecodeError, ValueError):
        raise ValueError("Invalid generation cursor") from None
    return parsed_at.astimezone(UTC).isoformat(), generation_id



def _encode_telegram_render_cursor(created_at: str, render_id: str) -> str:
    payload = f"{created_at}\n{render_id}".encode()
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def _decode_telegram_render_cursor(cursor: str) -> tuple[str, UUID]:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,512}", cursor):
        raise ValueError("Invalid render cursor")
    try:
        padding = "=" * (-len(cursor) % 4)
        payload = base64.b64decode(
            cursor + padding, altchars=b"-_", validate=True
        ).decode("utf-8")
        created_at, raw_render_id = payload.split("\n", 1)
        if not created_at or len(created_at) > 64:
            raise ValueError("Invalid render cursor")
        parsed_at = datetime.fromisoformat(created_at)
        if parsed_at.tzinfo is None or parsed_at.utcoffset() is None:
            raise ValueError("Invalid render cursor")
        render_id = UUID(raw_render_id)
        if str(render_id) != raw_render_id.lower():
            raise ValueError("Invalid render cursor")
    except (binascii.Error, UnicodeDecodeError, ValueError):
        raise ValueError("Invalid render cursor") from None
    return parsed_at.astimezone(UTC).isoformat(), render_id


def _stream_verified_media(file):
    """Stream the already verified open file, never reopening its storage path."""
    try:
        while chunk := file.read(1024 * 1024):
            yield chunk
    finally:
        file.close()


def _telegram_generation_summary(generation: dict[str, object]) -> dict[str, object]:
    """Expose only owner-safe lifecycle metadata; never provider IDs or private asset IDs."""
    allowed = (
        "generation_id",
        "provider",
        "model",
        "status",
        "progress_percent",
        "output_bytes",
        "output_duration_seconds",
        "output_width",
        "output_height",
        "error_code",
        "created_at",
        "updated_at",
    )
    return {key: generation.get(key) for key in allowed}


def _telegram_video_render_draft_summary(draft: dict[str, object]) -> dict[str, object]:
    """Expose only bounded draft metadata; never return source paths or timeline content."""
    renderer_timeline = draft.get("renderer_timeline")
    return {
        "draft_id": draft.get("draft_id"),
        "version": draft.get("version"),
        "duration_seconds": draft.get("duration_seconds"),
        "aspect_ratio": draft.get("aspect_ratio"),
        "renderer_ready": (
            isinstance(renderer_timeline, dict)
            and isinstance(draft.get("renderer_timeline_sha256"), str)
            and bool(draft.get("renderer_timeline_sha256"))
        ),
        "updated_at": draft.get("updated_at"),
    }


def _telegram_video_render_summary(render: dict[str, object]) -> dict[str, object]:
    """Expose render lifecycle metadata without leaking private media identifiers."""
    return {
        "render_id": render.get("render_id"),
        "render_kind": "deterministic_ffmpeg",
        "status": render.get("status"),
        "error_code": render.get("error_code"),
        "created_at": render.get("created_at"),
        "updated_at": render.get("updated_at"),
        "output_available": bool(render.get("output_asset_id")),
        "output_metadata": render.get("output_metadata"),
    }


def _pairing_repository() -> TelegramPairingRepository:
    return TelegramPairingRepository(get_settings().database_path)


def _tasks_repository() -> TaskRepository:
    repository = TaskRepository(get_settings().database_path)
    repository.initialize()
    return repository


@router.post("/pairing-challenges", status_code=201, response_model=PairingChallengeResponse)
def create_pairing_challenge(
    payload: PairingChallengeRequest,
    user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> PairingChallengeResponse:
    scopes = frozenset(payload.scopes)
    if len(scopes) != len(payload.scopes):
        raise HTTPException(status_code=422, detail="Duplicate Telegram scopes are not allowed")
    try:
        code, expires_at = _pairing_repository().create_challenge(
            owner_user_id=user.user_id,
            telegram_user_id=payload.telegram_user_id,
            client_id=str(payload.client_id),
            label=payload.label.strip(),
            scopes=scopes,
        )
    except TelegramPairingError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    AuditLogger(_tasks_repository()).record(
        event_type="telegram.pairing_challenge_created",
        outcome="success",
        subject_type="telegram_client",
        subject_id=str(payload.client_id),
        actor_type="user",
        actor_id=user.user_id,
        metadata={
            "client_id": str(payload.client_id),
            "telegram_user_id": payload.telegram_user_id,
            "scope_count": len(scopes),
        },
    )
    return PairingChallengeResponse(
        pairing_code=code,
        client_id=payload.client_id,
        expires_at=expires_at.isoformat(),
        scopes=sorted(scopes),
    )


@router.post("/exchange")
def exchange_pairing_code(payload: PairingExchangeRequest) -> dict[str, object]:
    try:
        result = _pairing_repository().exchange(
            pairing_code=payload.pairing_code,
            telegram_user_id=payload.telegram_user_id,
            client_id=str(payload.client_id),
        )
    except TelegramPairingError as exc:
        raise HTTPException(status_code=401, detail="Pairing code is invalid or expired") from exc
    AuditLogger(_tasks_repository()).record(
        event_type="telegram.client_paired",
        outcome="success",
        subject_type="telegram_client",
        subject_id=str(payload.client_id),
        actor_type="telegram_client",
        actor_id=str(payload.client_id),
        metadata={
            "client_id": str(payload.client_id),
            "telegram_user_id": payload.telegram_user_id,
            "scope_count": len(result["scopes"]),
        },
    )
    return result


@router.post("/refresh")
def refresh_telegram_access(payload: RefreshRequest) -> dict[str, object]:
    try:
        return _pairing_repository().refresh(
            refresh_token=payload.refresh_token,
            telegram_user_id=payload.telegram_user_id,
        )
    except TelegramPairingError as exc:
        raise HTTPException(status_code=401, detail="Refresh credential is invalid or revoked") from exc


@router.get("/clients")
def list_telegram_clients(
    user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> dict[str, object]:
    clients = _pairing_repository().list_clients(user.user_id)
    return {"clients": clients, "count": len(clients)}


@router.put("/clients/{client_id}/scopes")
def update_telegram_client_scopes(
    client_id: UUID,
    payload: ClientScopesUpdateRequest,
    user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> dict[str, object]:
    """Replace active-client scopes; the next paired request reads the updated allowlist."""
    scopes = frozenset(payload.scopes)
    if len(scopes) != len(payload.scopes):
        raise HTTPException(status_code=422, detail="Duplicate Telegram scopes are not allowed")
    updated_scopes = _pairing_repository().update_scopes(
        owner_user_id=user.user_id,
        client_id=str(client_id),
        scopes=scopes,
    )
    if updated_scopes is None:
        raise HTTPException(status_code=404, detail="Active Telegram client not found")
    AuditLogger(_tasks_repository()).record(
        event_type="telegram.client_scopes_updated",
        outcome="success",
        subject_type="telegram_client",
        subject_id=str(client_id),
        actor_type="user",
        actor_id=user.user_id,
        metadata={"client_id": str(client_id), "scope_count": len(updated_scopes)},
    )
    return {"client_id": str(client_id), "scopes": updated_scopes}


@router.post("/clients/{client_id}/revoke")
def revoke_telegram_client(
    client_id: UUID,
    user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> dict[str, bool]:
    revoked = _pairing_repository().revoke_client(
        owner_user_id=user.user_id,
        client_id=str(client_id),
    )
    if not revoked:
        raise HTTPException(status_code=404, detail="Active Telegram client not found")
    AuditLogger(_tasks_repository()).record(
        event_type="telegram.client_revoked",
        outcome="success",
        subject_type="telegram_client",
        subject_id=str(client_id),
        actor_type="user",
        actor_id=user.user_id,
        metadata={"client_id": str(client_id)},
    )
    return {"revoked": True}


@router.get("/status")
def telegram_status(
    identity: Annotated[TelegramClientIdentity, Depends(require_telegram_scope("status:read"))],
) -> dict[str, object]:
    return {
        "status": "authenticated",
        "client_id": identity.client_id,
        "label": identity.label,
        "scopes": sorted(identity.scopes),
    }


@router.get("/video/providers")
def list_telegram_video_providers(
    _identity: Annotated[
        TelegramClientIdentity, Depends(require_telegram_scope("video:read"))
    ],
) -> dict[str, object]:
    """Return the reviewed provider catalog without probing or starting work."""
    from mrhub.video_intelligence.generation_registry import video_generation_registry

    providers = [item.model_dump(mode="json") for item in video_generation_registry.catalog()]
    return {
        "providers": providers,
        "count": len(providers),
        "generation_available": bool(providers),
        "reason_code": None if providers else "provider_unavailable",
        "execution": "not_started",
    }


@router.post("/video/route-preview")
def preview_telegram_video_route(
    payload: GenerationRoutePreviewRequest,
    _identity: Annotated[
        TelegramClientIdentity, Depends(require_telegram_scope("video:read"))
    ],
) -> dict[str, object]:
    """Expose the same read-only routing policy to explicitly paired video:read clients."""
    return preview_hybrid_route(payload)


@router.get("/video/generations")
def list_telegram_video_generations(
    identity: Annotated[
        TelegramClientIdentity, Depends(require_telegram_scope("video:read"))
    ],
    limit: int = 10,
    cursor: str | None = None,
) -> dict[str, object]:
    """List bounded video-generation metadata for the paired owner's account."""
    if isinstance(limit, bool) or not 1 <= limit <= 20:
        raise HTTPException(status_code=422, detail="Video generation page limit must be between 1 and 20")
    before_created_at = None
    before_generation_id = None
    if cursor is not None:
        try:
            before_created_at, before_generation_id = _decode_telegram_generation_cursor(cursor)
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid video generation cursor") from None

    repository = VideoGenerationJobRepository(get_settings().database_path)
    rows = repository.list_for_owner(
        identity.owner_user_id,
        limit=limit + 1,
        before_created_at=before_created_at,
        before_generation_id=before_generation_id,
    )
    has_more = len(rows) > limit
    page = rows[:limit]
    last = page[-1] if page else None
    next_cursor = (
        _encode_telegram_generation_cursor(
            str(last["created_at"]), str(last["generation_id"])
        )
        if has_more and last is not None
        else None
    )
    return {
        "items": [_telegram_generation_summary(item) for item in page],
        "count": len(page),
        "has_more": has_more,
        "next_cursor": next_cursor,
    }


@router.get("/video/generations/{generation_id}")
def get_telegram_video_generation(
    generation_id: UUID,
    identity: Annotated[
        TelegramClientIdentity, Depends(require_telegram_scope("video:read"))
    ],
) -> dict[str, object]:
    """Return one generation only within the paired owner's account."""
    generation = VideoGenerationJobRepository(get_settings().database_path).get(
        identity.owner_user_id, generation_id
    )
    if generation is None:
        raise HTTPException(status_code=404, detail="Telegram video generation not found")
    return _telegram_generation_summary(generation)


@router.delete("/video/generations/{generation_id}")
def cancel_telegram_video_generation(
    generation_id: UUID,
    identity: Annotated[
        TelegramClientIdentity, Depends(require_telegram_scope("video:cancel"))
    ],
) -> dict[str, object]:
    """Cancel only a generation that has not been submitted to a provider."""
    repository = VideoGenerationJobRepository(get_settings().database_path)
    try:
        result = repository.cancel_pending(identity.owner_user_id, generation_id)
    except VideoGenerationCancellationConflict as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "generation_cancellation_conflict",
                "message": "Active or ambiguous provider work cannot be cancelled through this endpoint.",
            },
        ) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Telegram video generation not found")
    return result


@router.get("/video/render-drafts")
def list_telegram_video_render_drafts(
    identity: Annotated[
        TelegramClientIdentity, Depends(require_telegram_scope("video:read"))
    ],
    analysis_id: UUID,
) -> dict[str, object]:
    """List bounded, owner-scoped draft metadata for the deterministic local renderer."""
    analysis = VideoAnalysisJobRepository(get_settings().database_path).get(
        identity.owner_user_id, analysis_id
    )
    if analysis is None:
        raise HTTPException(status_code=404, detail="Telegram video analysis not found")
    if analysis.get("status") != "completed" or not isinstance(analysis.get("result"), dict):
        raise HTTPException(status_code=409, detail="Telegram video analysis is not completed")

    drafts = VideoTimelineDraftRepository(get_settings().database_path).list_for_analysis(
        identity.owner_user_id, analysis_id, limit=5
    )
    return {
        "analysis_id": str(analysis_id),
        "drafts": [_telegram_video_render_draft_summary(item) for item in drafts],
        "count": len(drafts),
    }


@router.get("/video/render-preflight")
def preflight_telegram_video_render(
    identity: Annotated[
        TelegramClientIdentity, Depends(require_telegram_scope("video:read"))
    ],
    draft_id: UUID,
) -> dict[str, object]:
    """Return a read-only local render preflight for this paired owner's draft."""
    try:
        return inspect_video_render_preflight(
            get_settings().database_path, identity.owner_user_id, draft_id
        )
    except LookupError as exc:
        raise HTTPException(
            status_code=404, detail="Telegram video timeline draft not found"
        ) from exc


@router.post("/video/renders", status_code=202)
def submit_telegram_video_render(
    payload: TelegramVideoRenderSubmissionRequest,
    response: Response,
    identity: Annotated[
        TelegramClientIdentity, Depends(require_telegram_scope("video:render"))
    ],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> dict[str, object]:
    """Queue a bounded local FFmpeg render from an exact owner-owned prepared draft."""
    database_path = get_settings().database_path
    draft = VideoTimelineDraftRepository(database_path).get(
        identity.owner_user_id, payload.draft_id
    )
    if draft is None:
        raise HTTPException(status_code=404, detail="Telegram video timeline draft not found")
    renderer_timeline_data = draft.get("renderer_timeline")
    if (
        not isinstance(renderer_timeline_data, dict)
        or not draft.get("renderer_timeline_sha256")
    ):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "renderer_timeline_not_saved",
                "message": "Prepare and save the renderer timeline in the Hub dashboard first",
            },
        )

    try:
        analysis_id = UUID(str(draft["analysis_id"]))
        draft_version = draft.get("version")
        if (
            isinstance(draft_version, bool)
            or not isinstance(draft_version, int)
            or draft_version < 1
        ):
            raise ValueError("Timeline draft version is invalid")
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=409, detail="Telegram video timeline draft is invalid"
        ) from exc

    analysis = VideoAnalysisJobRepository(database_path).get(
        identity.owner_user_id, analysis_id
    )
    if (
        analysis is None
        or analysis.get("status") != "completed"
        or not isinstance(analysis.get("result"), dict)
    ):
        raise HTTPException(status_code=409, detail="Telegram video analysis is not completed")
    assets = analysis["result"].get("assets")
    if not isinstance(assets, list):
        raise HTTPException(
            status_code=409, detail="Telegram video analysis assets are unavailable"
        )

    try:
        timeline = VideoTimeline.model_validate(renderer_timeline_data)
        snapshot = VideoRenderTimelineSnapshot.create(
            owner_user_id=identity.owner_user_id,
            analysis_id=analysis_id,
            draft_id=payload.draft_id,
            draft_version=draft_version,
            timeline=timeline,
            analysis_source_asset_ids=[
                str(item["asset_id"])
                for item in assets
                if isinstance(item, dict) and item.get("asset_id")
            ],
        )
        accepted, created = VideoRenderJobRepository(database_path).submit(
            identity.owner_user_id,
            analysis_id,
            idempotency_key,
            snapshot=snapshot,
        )
    except LookupError as exc:
        raise HTTPException(
            status_code=404, detail="Telegram video render source not found"
        ) from exc
    except VideoRenderSnapshotConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except VideoRenderConflict as exc:
        raise HTTPException(
            status_code=409, detail="Telegram video render idempotency conflict"
        ) from exc
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if not created:
        response.status_code = 200
    return {
        **{key: value for key, value in accepted.items() if key != "task_id"},
        "draft_id": str(payload.draft_id),
        "draft_version": draft_version,
        "created": created,
        "render_kind": "deterministic_ffmpeg",
    }



@router.get("/video/renders")
def list_telegram_video_renders(
    identity: Annotated[
        TelegramClientIdentity, Depends(require_telegram_scope("video:read"))
    ],
    limit: int = Query(default=10, ge=1, le=20),
    cursor: str | None = None,
) -> dict[str, object]:
    """List one bounded page of the paired owner's local deterministic renders."""
    before = None
    if cursor is not None:
        try:
            before = _decode_telegram_render_cursor(cursor)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="Invalid Telegram video render cursor") from exc

    repository = VideoRenderJobRepository(get_settings().database_path)
    records = repository.list_for_owner(
        identity.owner_user_id, limit=limit + 1, before=before
    )
    has_more = len(records) > limit
    page = records[:limit]
    renders = []
    for record in page:
        item = repository.get(identity.owner_user_id, UUID(record["render_id"]))
        if item is not None:
            renders.append(_telegram_video_render_summary(item))
    next_cursor = (
        _encode_telegram_render_cursor(page[-1]["created_at"], page[-1]["render_id"])
        if has_more and page
        else None
    )
    return {
        "renders": renders,
        "count": len(renders),
        "next_cursor": next_cursor,
        "render_kind": "deterministic_ffmpeg",
    }


@router.get("/video/renders/{render_id}")
def get_telegram_video_render(
    render_id: UUID,
    identity: Annotated[
        TelegramClientIdentity, Depends(require_telegram_scope("video:read"))
    ],
) -> dict[str, object]:
    """Return one local render only within the paired owner's account."""
    render = VideoRenderJobRepository(get_settings().database_path).get(
        identity.owner_user_id, render_id
    )
    if render is None:
        raise HTTPException(status_code=404, detail="Telegram video render not found")
    return _telegram_video_render_summary(render)



@router.get("/video/renders/{render_id}/file")
def download_telegram_video_render(
    render_id: UUID,
    identity: Annotated[
        TelegramClientIdentity, Depends(require_telegram_scope("video:read"))
    ],
):
    """Stream a completed owner-owned MP4 from the exact file verified by SHA-256."""
    database_path = get_settings().database_path
    render = VideoRenderJobRepository(database_path).get(
        identity.owner_user_id, render_id
    )
    if render is None:
        raise HTTPException(status_code=404, detail="Telegram video render not found")
    if render.get("status") != "completed" or not render.get("output_asset_id"):
        raise HTTPException(
            status_code=409,
            detail={"code": "telegram_video_render_not_completed"},
        )
    try:
        asset_id = UUID(str(render["output_asset_id"]))
    except (KeyError, TypeError, ValueError):
        raise HTTPException(status_code=404, detail="Telegram video render file not found") from None

    media = MediaAssetRepository(database_path)
    asset = media.get(identity.owner_user_id, asset_id)
    if (
        asset is None
        or asset.get("media_type") != "video/mp4"
        or asset.get("processing_status") not in {"stored", "processed"}
    ):
        raise HTTPException(status_code=404, detail="Telegram video render file not found")
    storage_key = asset.get("storage_key")
    if not isinstance(storage_key, str):
        raise HTTPException(status_code=404, detail="Telegram video render file not found")
    recorded_size = asset.get("file_size")
    if (
        isinstance(recorded_size, bool)
        or not isinstance(recorded_size, int)
        or not 1 <= recorded_size <= MAX_OUTPUT_BYTES
    ):
        raise HTTPException(status_code=404, detail="Telegram video render file not found")
    if recorded_size > MAX_TELEGRAM_VIDEO_BYTES:
        raise HTTPException(
            status_code=413,
            detail={"code": "telegram_video_render_too_large", "max_bytes": MAX_TELEGRAM_VIDEO_BYTES},
        )
    try:
        path = media.file_path(storage_key)
    except (OSError, ValueError):
        raise HTTPException(status_code=404, detail="Telegram video render file not found") from None

    stream = None
    try:
        stream = path.open("rb")
        opened_stat = os.fstat(stream.fileno())
        file_size = opened_stat.st_size
        if (
            not stat.S_ISREG(opened_stat.st_mode)
            or file_size != recorded_size
            or not 1 <= file_size <= MAX_OUTPUT_BYTES
        ):
            raise ValueError("invalid_media_file")
        digest = hashlib.sha256()
        header = stream.read(12)
        if len(header) < 12 or header[4:8] != b"ftyp":
            raise ValueError("invalid_mp4_signature")
        digest.update(header)
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
        expected_hash = asset.get("content_hash")
        if not isinstance(expected_hash, str) or digest.hexdigest() != expected_hash:
            raise ValueError("media_checksum_mismatch")
        final_stat = os.fstat(stream.fileno())
        if (
            final_stat.st_size != opened_stat.st_size
            or final_stat.st_mtime_ns != opened_stat.st_mtime_ns
        ):
            raise ValueError("media_changed_during_verification")
        stream.seek(0)
    except (OSError, ValueError):
        if stream is not None:
            stream.close()
        raise HTTPException(status_code=404, detail="Telegram video render file not found") from None

    filename = f"render-{render_id}.mp4"
    return StreamingResponse(
        _stream_verified_media(stream),
        media_type="video/mp4",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(file_size),
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
        background=BackgroundTask(stream.close),
    )


@router.delete("/video/renders/{render_id}")
def cancel_telegram_video_render(
    render_id: UUID,
    identity: Annotated[
        TelegramClientIdentity, Depends(require_telegram_scope("video:cancel"))
    ],
) -> dict[str, object]:
    """Cancel or signal cancellation for a render owned by this paired client."""
    result = VideoRenderJobRepository(get_settings().database_path).cancel(
        identity.owner_user_id, render_id
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Telegram video render not found")
    return {
        "render_id": result["render_id"],
        "render_kind": "deterministic_ffmpeg",
        "status": result["status"],
        "cancellation_requested": bool(result.get("cancellation_requested", False)),
    }


@router.get("/tasks")
def list_telegram_tasks(
    identity: Annotated[TelegramClientIdentity, Depends(require_telegram_scope("tasks:read"))],
    limit: int = 20,
    cursor: str | None = None,
    status: TaskStatus | None = None,
) -> dict[str, object]:
    """List this paired client's recent tasks; pass next_cursor unchanged for older pages."""
    if not 1 <= limit <= 50:
        raise HTTPException(status_code=422, detail="Limit must be between 1 and 50")
    try:
        before = _decode_telegram_task_cursor(cursor) if cursor is not None else None
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid task cursor") from None
    tasks, has_more, cursor_after = _tasks_repository().list_recent_for_telegram_client(
        identity.client_id,
        limit,
        before=before,
        status=status,
    )
    next_cursor = _encode_telegram_task_cursor(*cursor_after) if cursor_after else None
    return {
        "tasks": [task.model_dump(mode="json") for task in tasks],
        "count": len(tasks),
        "has_more": has_more,
        "next_cursor": next_cursor,
    }


@router.get("/tasks/{task_id}")
def get_telegram_task(
    task_id: UUID,
    identity: Annotated[TelegramClientIdentity, Depends(require_telegram_scope("tasks:read"))],
) -> dict[str, object]:
    """Return one task only to the exact paired client that submitted it."""
    task = _tasks_repository().get_for_telegram_client(identity.client_id, task_id)
    if task is None:
        # Do not reveal whether another bot client or an owner created this task.
        raise HTTPException(status_code=404, detail="Telegram task not found")
    return task.model_dump(mode="json")


@router.get("/tasks/{task_id}/events")
def get_telegram_task_events(
    task_id: UUID,
    identity: Annotated[TelegramClientIdentity, Depends(require_telegram_scope("tasks:read"))],
    limit: int = 20,
    cursor: str | None = None,
) -> dict[str, object]:
    """Return one stable, bounded audit page for the exact paired client's task."""
    if not 1 <= limit <= 50:
        raise HTTPException(status_code=422, detail="Limit must be between 1 and 50")
    before = None
    if cursor is not None:
        try:
            before = _decode_telegram_task_event_cursor(cursor)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="Invalid task event cursor") from exc
    repository = _tasks_repository()
    if repository.get_for_telegram_client(identity.client_id, task_id) is None:
        raise HTTPException(status_code=404, detail="Telegram task not found")
    page = repository.list_task_audit_event_page(task_id, limit, before=before)
    events = page["events"]
    next_cursor = None
    if page["has_more"] and events:
        last = events[-1]
        next_cursor = _encode_telegram_task_event_cursor(
            str(last["created_at"]), str(last["event_id"])
        )
    return {
        "task_id": str(task_id),
        "events": events,
        "count": len(events),
        "has_more": page["has_more"],
        "next_cursor": next_cursor,
    }


@router.get("/tasks/{task_id}/result")
def get_telegram_task_result(
    task_id: UUID,
    identity: Annotated[TelegramClientIdentity, Depends(require_telegram_scope("tasks:result"))],
) -> dict[str, object]:
    """Return a bounded terminal result only to the paired client that submitted the task."""
    repository = _tasks_repository()
    task = repository.get_for_telegram_client(identity.client_id, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Telegram task not found")
    if task.status not in {
        TaskStatus.SUCCEEDED,
        TaskStatus.FAILED,
        TaskStatus.CANCELLED,
        TaskStatus.REJECTED,
    }:
        raise HTTPException(status_code=409, detail="Telegram task result is not ready")
    result = WorkerEngine(repository).get_result(task_id)
    if result is None:
        raise HTTPException(status_code=409, detail="Telegram task result is not ready")
    encoded = json.dumps(result, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(encoded) > 32_768:
        raise HTTPException(status_code=413, detail="Telegram task result exceeds the response limit")
    return result


@router.post("/tasks/{task_id}/cancel")
def cancel_telegram_task(
    task_id: UUID,
    identity: Annotated[TelegramClientIdentity, Depends(require_telegram_scope("tasks:cancel"))],
) -> dict[str, object]:
    """Cancel a task only while it is queued or waiting for owner approval."""
    repository = _tasks_repository()
    task = repository.get_for_telegram_client(identity.client_id, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Telegram task not found")
    try:
        cancelled = JobEngine(repository).cancel_pending(task_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Telegram task not found") from exc
    except (InvalidTaskTransition, RuntimeError) as exc:
        raise HTTPException(status_code=409, detail="Telegram task is no longer cancellable") from exc
    AuditLogger(repository).record(
        event_type="telegram.task_cancelled",
        outcome="success",
        subject_type="task",
        subject_id=str(task_id),
        actor_type="telegram_client",
        actor_id=identity.client_id,
        metadata={"client_id": identity.client_id, "previous_status": task.status.value},
    )
    return cancelled.model_dump(mode="json")


@router.post("/tasks", status_code=201)
def create_telegram_task(
    payload: TaskCreateRequest,
    identity: Annotated[TelegramClientIdentity, Depends(require_telegram_scope("tasks:create"))],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=255)],
    response: Response,
) -> dict[str, object]:
    policy = PolicyEngine()
    risk_class = policy.classify_task_type(payload.task_type)
    decision = policy.evaluate(ActionRequest(action="task.submit", risk_class=risk_class))
    if decision.decision is PolicyDecision.DENY:
        raise HTTPException(status_code=403, detail=decision.reason)
    task = TaskRecord(
        task_type=payload.task_type,
        description=payload.description,
        risk_class=risk_class,
        status=(
            TaskStatus.WAITING_APPROVAL
            if decision.decision is PolicyDecision.REQUIRE_APPROVAL
            else TaskStatus.QUEUED
        ),
    )
    canonical = json.dumps(
        {
            "task_type": task.task_type,
            "description": task.description,
            "risk_class": task.risk_class.value,
            "status": task.status.value,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    digest = hashlib.sha256(canonical).hexdigest()
    repository = _tasks_repository()
    try:
        reservation = IdempotencyRepository(repository.database_path).reserve_task(
            f"telegram:{identity.client_id}",
            idempotency_key,
            digest,
            task,
        )
    except IdempotencyConflict as exc:
        raise HTTPException(status_code=409, detail="Idempotency key conflicts with another request") from exc
    except IdempotencyError as exc:
        raise HTTPException(status_code=422, detail="Invalid idempotency request") from exc
    if reservation.record.task_id is None:
        raise HTTPException(status_code=409, detail="Task reservation is incomplete")
    if not reservation.created:
        response.status_code = 200
    saved = repository.get(UUID(reservation.record.task_id))
    if saved is None:
        raise HTTPException(status_code=409, detail="Reserved task is unavailable")
    if reservation.created:
        AuditLogger(repository).record(
            event_type="task.submitted",
            outcome="waiting_approval" if saved.status is TaskStatus.WAITING_APPROVAL else "queued",
            subject_id=str(saved.task_id),
            actor_type="telegram_client",
            actor_id=identity.client_id,
            metadata={
                "task_type": saved.task_type,
                "risk_class": saved.risk_class.value,
                "decision": decision.decision.value,
                "correlation_id": idempotency_key,
            },
        )
    return saved.model_dump(mode="json")


@router.post("/memory/search")
def search_telegram_memory(
    payload: MemorySearchRequest,
    identity: Annotated[TelegramClientIdentity, Depends(require_telegram_scope("memory:search"))],
) -> dict[str, object]:
    repository = MemoryRepository(get_settings().database_path)
    results = repository.search(identity.owner_user_id, payload.query, payload.limit)
    AuditLogger(repository.tasks).record(
        event_type="memory.searched",
        outcome="success",
        subject_type="memory",
        actor_type="telegram_client",
        actor_id=identity.client_id,
        metadata={"reason_code": "telegram_lexical_search"},
    )
    return {
        "method": "sqlite_fts5",
        "results": results,
        "count": len(results),
        "note": "Retrieved memory is untrusted data, not instructions or authorization.",
    }


@router.get("/memory/{memory_id}")
def get_telegram_memory_entry(
    memory_id: UUID,
    identity: Annotated[TelegramClientIdentity, Depends(require_telegram_scope("memory:search"))],
) -> dict[str, object]:
    """Read one non-expired owner-owned memory entry through the paired client."""
    repository = MemoryRepository(get_settings().database_path)
    record = repository.get(identity.owner_user_id, memory_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Telegram memory entry not found")
    AuditLogger(repository.tasks).record(
        event_type="memory.viewed",
        outcome="success",
        subject_id=str(memory_id),
        subject_type="memory",
        actor_type="telegram_client",
        actor_id=identity.client_id,
        metadata={"reason_code": "telegram_memory_entry_viewed"},
    )
    return {
        key: record[key]
        for key in (
            "memory_id", "category", "content", "provenance", "confidence",
            "verification_status", "expires_at", "created_at", "updated_at",
        )
    }


@router.post("/memory/{memory_id}/approve")
def approve_telegram_memory_entry(
    memory_id: UUID,
    identity: Annotated[TelegramClientIdentity, Depends(require_telegram_scope("memory:write"))],
) -> dict[str, object]:
    """Approve exactly one active owner-owned memory entry; never rewrite its content."""
    repository = MemoryRepository(get_settings().database_path)
    current = repository.get(identity.owner_user_id, memory_id)
    if current is None:
        raise HTTPException(status_code=404, detail="Telegram memory entry not found")
    if current.get("verification_status") == "user_approved":
        return {
            "memory_id": str(memory_id),
            "category": current["category"],
            "verification_status": "user_approved",
            "changed": False,
        }
    updated = repository.update(
        identity.owner_user_id, memory_id, {"verification_status": "user_approved"}
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Telegram memory entry not found")
    AuditLogger(repository.tasks).record(
        event_type="memory.approved",
        outcome="success",
        subject_id=str(memory_id),
        subject_type="memory",
        actor_type="telegram_client",
        actor_id=identity.client_id,
        metadata={"reason_code": "explicit_telegram_owner_approval"},
    )
    return {
        "memory_id": str(memory_id),
        "category": updated["category"],
        "verification_status": "user_approved",
        "changed": True,
    }


@router.post("/memory/validate/preview")
def preview_telegram_memory_validation(
    payload: MemoryValidationPreviewRequest,
    identity: Annotated[TelegramClientIdentity, Depends(require_telegram_scope("memory:search"))],
) -> dict[str, object]:
    """Return owner-scoped validation hints through the paired private client."""
    settings = get_settings()
    result = MemoryValidationEngine(settings.database_path).preview(
        identity.owner_user_id,
        limit=payload.limit,
        threshold=payload.similarity_threshold,
    )
    repository = MemoryRepository(settings.database_path)
    AuditLogger(repository.tasks).record(
        event_type="memory.validation_previewed",
        outcome="success",
        subject_type="memory_validation",
        actor_type="telegram_client",
        actor_id=identity.client_id,
        metadata={
            "entries_scanned": result["entries_scanned"],
            "expired_count": result["expired_count"],
            "unverified_count": result["unverified_count"],
            "contradiction_count": result["contradiction_count"],
            "state_changed": False,
        },
    )
    return result


@router.post("/memory/dream/preview")
def preview_telegram_memory_dreaming(
    payload: MemoryDreamPreviewRequest,
    identity: Annotated[TelegramClientIdentity, Depends(require_telegram_scope("memory:search"))],
) -> dict[str, object]:
    """Return owner-scoped consolidation hints through the paired private client."""
    settings = get_settings()
    result = MemoryDreamingEngine(settings.database_path).preview(
        identity.owner_user_id,
        limit=payload.limit,
        threshold=payload.similarity_threshold,
    )
    repository = MemoryRepository(settings.database_path)
    AuditLogger(repository.tasks).record(
        event_type="memory.dream_previewed",
        outcome="success",
        subject_type="memory_dream",
        actor_type="telegram_client",
        actor_id=identity.client_id,
        metadata={
            "entries_scanned": result["entries_scanned"],
            "proposal_count": result["proposal_count"],
            "state_changed": False,
        },
    )
    return result

