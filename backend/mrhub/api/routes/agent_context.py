"""Authenticated, bounded Agent Context assembly endpoint."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator

from mrhub.agents.context import AgentContextAssembler
from mrhub.api.dependencies import require_user
from mrhub.config import get_settings
from mrhub.infrastructure.database import TaskRepository
from mrhub.security.audit import AuditLogger
from mrhub.security.auth import AuthenticatedUser

router = APIRouter(
    prefix="/agent/context",
    tags=["agent-context"],
    dependencies=[Depends(require_user)],
)


class AgentContextRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=200)
    include_memory: bool = Field(default=True, strict=True)
    include_knowledge: bool = Field(default=True, strict=True)

    @field_validator("query")
    @classmethod
    def normalize_query(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized or len(normalized) > 200:
            raise ValueError("Query must contain 1 to 200 non-whitespace characters")
        return normalized
    knowledge_freshness_policy: Literal[
        "include_all", "owner_reviewed_current_only"
    ] = "include_all"
    memory_types: list[Literal["unspecified", "episodic", "semantic", "procedural"]] | None = Field(
        default=None, max_length=4
    )


@router.post("/assemble")
def assemble_agent_context(
    payload: AgentContextRequest,
    user: Annotated[AuthenticatedUser, Depends(require_user)],
    response: Response,
) -> dict[str, object]:
    """Return bounded owner-scoped evidence for a future model-facing caller."""
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["Pragma"] = "no-cache"
    response.headers["X-Content-Type-Options"] = "nosniff"
    settings = get_settings()
    assembler = AgentContextAssembler(settings.database_path)
    try:
        result = assembler.assemble(
            user.user_id,
            query=payload.query,
            include_memory=payload.include_memory,
            include_knowledge=payload.include_knowledge,
            knowledge_freshness_policy=payload.knowledge_freshness_policy,
            memory_types=payload.memory_types,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Invalid context query") from exc

    # Audit only the operation and result counts; never log the query or passages.
    audit = AuditLogger(TaskRepository(settings.database_path))
    audit.record(
        event_type="agent.context_assembled",
        outcome="success",
        subject_type="agent_context",
        subject_id=None,
        actor_type="user",
        actor_id=user.user_id,
        metadata={
            "memory_included": payload.include_memory,
            "knowledge_included": payload.include_knowledge,
            "memory_type_filter_count": len(payload.memory_types or []),
            "passage_count": result["passage_count"],
            "retrieval_method": result["retrieval_method"],
        },
    )
    return result
