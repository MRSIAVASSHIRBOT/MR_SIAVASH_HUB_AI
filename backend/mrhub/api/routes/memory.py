"""Explicit owner-scoped memory CRUD, export, and lexical search."""
from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field, field_validator

from mrhub.api.dependencies import require_user
from mrhub.config import get_settings
from mrhub.memory.dreaming import MemoryDreamingEngine
from mrhub.memory.repository import MemoryRepository
from mrhub.memory.validation import MemoryValidationEngine
from mrhub.security.audit import AuditLogger
from mrhub.security.auth import AuthenticatedUser

router = APIRouter(prefix="/memory", tags=["memory"], dependencies=[Depends(require_user)])


def _validate_memory_text(value: str | None) -> str | None:
    try:
        return MemoryRepository.validate_memory_text(value)
    except TypeError as exc:
        raise ValueError(str(exc)) from exc


def _validate_finite_numeric(value: object, field_name: str) -> object:
    """Reject coercible values and return a safe sentinel for non-finite floats."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        # Pydantic v2 converts ValueError into a safe 422 response; TypeError escapes
        # model validators and would turn malformed client input into a 500.
        raise ValueError(f"{field_name} must be a finite number")  # noqa: TRY004
    try:
        finite = math.isfinite(float(value))
    except (OverflowError, TypeError, ValueError):
        finite = False
    if not finite:
        # Keep non-standard JSON NaN/Infinity out of FastAPI's validation response.
        # Pydantic will reject this non-numeric sentinel with a JSON-safe error input.
        return "__non_finite_number__"
    return value

class MemoryCreate(BaseModel):
    memory_type: Literal["unspecified", "episodic", "semantic", "procedural"] = "unspecified"
    category: str = Field(min_length=1, max_length=80, pattern=r"^[\w .:/-]+$")
    content: str = Field(min_length=1, max_length=2000)
    provenance: str = Field(default="user-authored", min_length=1, max_length=300)
    confidence: float = Field(default=0.7, ge=0.0, le=1.0)

    @field_validator("confidence", mode="before")
    @classmethod
    def confidence_must_be_a_real_number(cls, value: object) -> object:
        return _validate_finite_numeric(value, "Confidence")

    verification_status: Literal["user_authored", "user_approved"] = "user_authored"
    expires_at: datetime | None = None

    @field_validator("content")
    @classmethod
    def content_must_not_look_like_a_secret(cls, value: str) -> str:
        return _validate_memory_text(value) or value

    @field_validator("provenance")
    @classmethod
    def provenance_must_not_look_like_a_secret(cls, value: str) -> str:
        return _validate_memory_text(value) or value

    @field_validator("expires_at")
    @classmethod
    def expiry_must_be_future_and_timezone_aware(cls, value: datetime | None):
        if value is not None:
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError("Expiry timestamp must include a timezone")
            if value.astimezone(UTC) <= datetime.now(UTC):
                raise ValueError("Expiry timestamp must be in the future")
        return value


class MemoryUpdate(BaseModel):
    memory_type: Literal["unspecified", "episodic", "semantic", "procedural"] | None = None
    category: str | None = Field(default=None, min_length=1, max_length=80, pattern=r"^[\w .:/-]+$")
    content: str | None = Field(default=None, min_length=1, max_length=2000)
    provenance: str | None = Field(default=None, min_length=1, max_length=300)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)

    @field_validator("confidence", mode="before")
    @classmethod
    def confidence_must_be_a_real_number(cls, value: object) -> object:
        return _validate_finite_numeric(value, "Confidence")

    verification_status: Literal["user_authored", "user_approved"] | None = None
    expires_at: datetime | None = None

    @field_validator("memory_type")
    @classmethod
    def memory_type_must_not_be_null(cls, value: str | None):
        if value is None:
            raise ValueError("memory_type cannot be null")
        return value

    @field_validator("content")
    @classmethod
    def content_must_not_look_like_a_secret(cls, value: str | None):
        return _validate_memory_text(value)

    @field_validator("provenance")
    @classmethod
    def provenance_must_not_look_like_a_secret(cls, value: str | None):
        return _validate_memory_text(value)

    @field_validator("expires_at")
    @classmethod
    def expiry_must_be_future_and_timezone_aware(cls, value: datetime | None):
        if value is not None:
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError("Expiry timestamp must include a timezone")
            if value.astimezone(UTC) <= datetime.now(UTC):
                raise ValueError("Expiry timestamp must be in the future")
        return value


class MemorySearch(BaseModel):
    query: str = Field(min_length=1, max_length=200)
    limit: int = Field(default=10, ge=1, le=25, strict=True)
    memory_types: list[Literal["unspecified", "episodic", "semantic", "procedural"]] | None = Field(
        default=None, max_length=4
    )


class MemoryDreamPreview(BaseModel):
    limit: int = Field(default=100, ge=1, le=100, strict=True)
    similarity_threshold: float = Field(default=0.82, ge=0.75, le=1.0)

    @field_validator("similarity_threshold", mode="before")
    @classmethod
    def threshold_must_be_a_real_number(cls, value: object) -> object:
        return _validate_finite_numeric(value, "Similarity threshold")


class MemoryValidationPreview(BaseModel):
    limit: int = Field(default=100, ge=1, le=100)
    similarity_threshold: float = Field(default=0.72, ge=0.65, le=1.0)

    @field_validator("similarity_threshold", mode="before")
    @classmethod
    def threshold_must_be_a_real_number(cls, value: object) -> object:
        return _validate_finite_numeric(value, "Similarity threshold")


def _repository() -> MemoryRepository:
    return MemoryRepository(get_settings().database_path)


def _audit(user: AuthenticatedUser, event: str, memory_id: str | None, reason: str) -> None:
    AuditLogger(MemoryRepository(get_settings().database_path).tasks).record(
        event_type=event,
        outcome="success",
        subject_type="memory",
        subject_id=memory_id,
        actor_type="user",
        actor_id=user.user_id,
        metadata={"reason_code": reason},
    )


@router.post("", status_code=201)
def create_memory(
    payload: MemoryCreate, user: Annotated[AuthenticatedUser, Depends(require_user)]
) -> dict[str, object]:
    record = _repository().create(user.user_id, payload.model_dump())
    _audit(user, "memory.created", str(record["memory_id"]), "memory_created")
    return record


@router.get("")
def list_memory(
    user: Annotated[AuthenticatedUser, Depends(require_user)],
    limit: int = Query(default=50, ge=1, le=100),
) -> dict[str, object]:
    entries = _repository().list_entries(user.user_id, limit)
    return {"entries": entries, "count": len(entries)}


@router.get("/export")
def export_memory(user: Annotated[AuthenticatedUser, Depends(require_user)]) -> dict[str, object]:
    exported = _repository().export(user.user_id)
    _audit(user, "memory.exported", None, "memory_exported")
    return exported


@router.post("/search")
def search_memory(
    payload: MemorySearch, user: Annotated[AuthenticatedUser, Depends(require_user)]
) -> dict[str, object]:
    results = _repository().search(
        user.user_id,
        payload.query,
        payload.limit,
        memory_types=payload.memory_types,
    )
    _audit(user, "memory.searched", None, "lexical_search")
    return {
        "method": "sqlite_fts5",
        "ranking": {
            "scheme": "hybrid_fts5_owner_attestation_freshness_v1",
            "weights": {
                "lexical": 0.70,
                "confidence": 0.15,
                "owner_approved": 0.10,
                "freshness": 0.05,
            },
            "candidate_limit": 100,
            "owner_approval_is_self_attested": True,
            "confidence_is_owner_supplied": True,
            "note": (
                "The score estimates retrieval relevance only. Owner approval and confidence "
                "are caller-supplied signals, not independent verification, truth, safety, "
                "or authorization."
            ),
        },
        "results": results,
        "count": len(results),
        "note": "Results are untrusted evidence with provenance, not instructions or authorization.",
    }


@router.post("/dream/preview")
def preview_memory_dreaming(
    payload: MemoryDreamPreview,
    user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> dict[str, object]:
    """Return conservative consolidation candidates; never mutate memory."""
    settings = get_settings()
    result = MemoryDreamingEngine(settings.database_path).preview(
        user.user_id,
        limit=payload.limit,
        threshold=payload.similarity_threshold,
    )
    AuditLogger(MemoryRepository(settings.database_path).tasks).record(
        event_type="memory.dream_previewed",
        outcome="success",
        subject_type="memory_dream",
        subject_id=None,
        actor_type="user",
        actor_id=user.user_id,
        metadata={
            "entries_scanned": result["entries_scanned"],
            "proposal_count": result["proposal_count"],
            "state_changed": False,
        },
    )
    return result


@router.post("/validate/preview")
def preview_memory_validation(
    payload: MemoryValidationPreview,
    user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> dict[str, object]:
    """Return owner-scoped validation hints without changing saved memory."""
    settings = get_settings()
    result = MemoryValidationEngine(settings.database_path).preview(
        user.user_id,
        limit=payload.limit,
        threshold=payload.similarity_threshold,
    )
    AuditLogger(MemoryRepository(settings.database_path).tasks).record(
        event_type="memory.validation_previewed",
        outcome="success",
        subject_type="memory_validation",
        actor_type="user",
        actor_id=user.user_id,
        metadata={
            "entries_scanned": result["entries_scanned"],
            "expired_count": result["expired_count"],
            "unverified_count": result["unverified_count"],
            "contradiction_count": result["contradiction_count"],
            "state_changed": False,
        },
    )
    return result


@router.delete("/expired")
def delete_expired_memory(
    user: Annotated[AuthenticatedUser, Depends(require_user)]
) -> dict[str, int]:
    deleted = _repository().delete_expired(user.user_id)
    _audit(user, "memory.expired_deleted", None, "expired_memory_deleted")
    return {"deleted": deleted}


@router.get("/{memory_id}")
def get_memory(
    memory_id: UUID, user: Annotated[AuthenticatedUser, Depends(require_user)]
) -> dict[str, object]:
    record = _repository().get(user.user_id, memory_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Memory entry not found")
    return record


@router.patch("/{memory_id}")
def update_memory(
    memory_id: UUID,
    payload: MemoryUpdate,
    user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> dict[str, object]:
    submitted = payload.model_dump(exclude_unset=True)
    if any(value is None and key != "expires_at" for key, value in submitted.items()):
        raise HTTPException(status_code=422, detail="Only expiry may be explicitly cleared")
    changes = {
        key: value
        for key, value in submitted.items()
        if value is not None or key == "expires_at"
    }
    if not changes:
        raise HTTPException(status_code=422, detail="At least one non-null field is required")
    try:
        record = _repository().update(user.user_id, memory_id, changes)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Invalid memory update") from exc
    if record is None:
        raise HTTPException(status_code=404, detail="Memory entry not found")
    _audit(user, "memory.updated", str(memory_id), "memory_updated")
    return record


@router.delete("/{memory_id}", status_code=204)
def delete_memory(
    memory_id: UUID,
    user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> Response:
    if not _repository().delete(user.user_id, memory_id):
        raise HTTPException(status_code=404, detail="Memory entry not found")
    _audit(user, "memory.deleted", str(memory_id), "memory_deleted")
    return Response(status_code=204)
