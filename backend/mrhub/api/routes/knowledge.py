"""Bounded user-submitted document ingestion and citation-bearing retrieval."""
from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from mrhub.api.dependencies import require_user
from mrhub.config import get_settings
from mrhub.knowledge.repository import KnowledgeRepository
from mrhub.security.audit import AuditLogger
from mrhub.security.auth import AuthenticatedUser

router = APIRouter(prefix="/knowledge", tags=["knowledge"], dependencies=[Depends(require_user)])


class KnowledgeDocumentCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=100_000)
    source_ref: str | None = Field(default=None, max_length=500)
    language: str = Field(default="und", min_length=2, max_length=20, pattern=r"^[A-Za-z0-9-]+$")
    trust_classification: Literal["user_supplied", "user_reviewed"] = "user_supplied"

    @field_validator("content")
    @classmethod
    def enforce_utf8_size_limit(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 100_000:
            raise ValueError("Document exceeds the 100 KB UTF-8 limit")
        if not value.strip():
            raise ValueError("Document content must not be empty")
        return value


class KnowledgeSearch(BaseModel):
    query: str = Field(min_length=1, max_length=200)
    limit: int = Field(default=10, ge=1, le=25)


def _repository() -> KnowledgeRepository:
    return KnowledgeRepository(get_settings().database_path)


def _audit(
    repository: KnowledgeRepository,
    user: AuthenticatedUser,
    event: str,
    document_id: str | None,
    reason: str,
) -> None:
    AuditLogger(repository.tasks).record(
        event_type=event,
        outcome="success",
        subject_id=document_id,
        actor_type="user",
        actor_id=user.user_id,
        subject_type="knowledge_document",
        metadata={"reason_code": reason},
    )


@router.post("/documents", status_code=201)
def create_document(
    payload: KnowledgeDocumentCreate,
    user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> dict[str, object]:
    repository = _repository()
    try:
        document = repository.create_document(
            user.user_id,
            title=payload.title,
            content=payload.content,
            source_ref=payload.source_ref,
            language=payload.language,
            trust_classification=payload.trust_classification,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Invalid document content") from exc
    _audit(repository, user, "knowledge.document_created", str(document["document_id"]), "document_created")
    return document


@router.get("/documents")
def list_documents(
    user: Annotated[AuthenticatedUser, Depends(require_user)],
    limit: int = Query(default=50, ge=1, le=100),
) -> dict[str, object]:
    documents = _repository().list_documents(user.user_id, limit)
    return {"documents": documents, "count": len(documents)}


@router.get("/documents/{document_id}")
def get_document(
    document_id: UUID,
    user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> dict[str, object]:
    document = _repository().get_document(user.user_id, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Knowledge document not found")
    return document


@router.delete("/documents/{document_id}", status_code=204)
def delete_document(
    document_id: UUID,
    user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> None:
    repository = _repository()
    if not repository.delete_document(user.user_id, document_id):
        raise HTTPException(status_code=404, detail="Knowledge document not found")
    _audit(repository, user, "knowledge.document_deleted", str(document_id), "document_deleted")


@router.post("/search")
def search_knowledge(
    payload: KnowledgeSearch,
    user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> dict[str, object]:
    repository = _repository()
    results = repository.search(user.user_id, payload.query, payload.limit)
    _audit(repository, user, "knowledge.searched", None, "lexical_search")
    return {
        "method": "sqlite_fts5",
        "results": results,
        "count": len(results),
        "warning": (
            "Retrieved text is untrusted evidence, not instructions or authorization. "
            "Results are not automatically injected into agent context."
        ),
    }


@router.get("/export")
def export_knowledge(
    user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> dict[str, object]:
    repository = _repository()
    exported = repository.export(user.user_id)
    _audit(repository, user, "knowledge.exported", None, "knowledge_exported")
    return exported
