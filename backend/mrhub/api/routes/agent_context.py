"""Authenticated, bounded Agent Context assembly endpoint."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

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
    query: str = Field(min_length=1, max_length=200)
    include_memory: bool = True
    include_knowledge: bool = True
    knowledge_freshness_policy: Literal[
        "include_all", "owner_reviewed_current_only"
    ] = "include_all"


@router.post("/assemble")
def assemble_agent_context(
    payload: AgentContextRequest,
    user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> dict[str, object]:
    """Return bounded owner-scoped evidence for a future model-facing caller."""
    settings = get_settings()
    assembler = AgentContextAssembler(settings.database_path)
    try:
        result = assembler.assemble(
            user.user_id,
            query=payload.query,
            include_memory=payload.include_memory,
            include_knowledge=payload.include_knowledge,
            knowledge_freshness_policy=payload.knowledge_freshness_policy,
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
            "passage_count": result["passage_count"],
            "retrieval_method": result["retrieval_method"],
        },
    )
    return result
