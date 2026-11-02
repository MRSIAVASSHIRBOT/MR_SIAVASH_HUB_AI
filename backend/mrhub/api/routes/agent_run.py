"""Authenticated bounded model-driven Agent execution with explicit provider mode."""

from __future__ import annotations

import json
from typing import Annotated, Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from mrhub.agents.context import AgentContextAssembler
from mrhub.agents.orchestrator import AgentLoopRequest, AgentOrchestrator
from mrhub.api.dependencies import require_user
from mrhub.api.routes.models import build_model_router
from mrhub.config import get_settings
from mrhub.infrastructure.database import TaskRepository
from mrhub.providers.router import ModelRequest
from mrhub.security.audit import AuditLogger
from mrhub.security.auth import AuthenticatedUser
from mrhub.tools.builtins import build_tool_registry

router = APIRouter(prefix="/agent", tags=["agent"], dependencies=[Depends(require_user)])


class AgentRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    goal: str = Field(min_length=1, max_length=1_000)
    context_query: str | None = Field(default=None, min_length=1, max_length=200)
    provider_mode: Literal["local", "remote"] = "local"
    include_memory: bool = True
    include_knowledge: bool = True
    max_turns: int = Field(default=3, ge=1, le=3)
    max_output_tokens: int = Field(default=512, ge=1, le=512)


@router.post("/run")
def run_agent(
    payload: AgentRunRequest,
    user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> dict[str, object]:
    """Run one explicitly bounded model loop; no stub or provider fallback is permitted."""
    settings = get_settings()
    model_router = build_model_router(
        provider_mode=payload.provider_mode,
        include_stub=False,
    )
    try:
        model_router.select(
            ModelRequest(
                requires_text=True,
                prefer_local=payload.provider_mode == "local",
            )
        )
    except LookupError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Requested {payload.provider_mode} inference provider is disabled or unavailable",
        ) from exc

    query = (payload.context_query or payload.goal)[:200]
    context = AgentContextAssembler(settings.database_path).assemble(
        user.user_id,
        query=query,
        include_memory=payload.include_memory,
        include_knowledge=payload.include_knowledge,
    )
    evidence = json.dumps(
        context["passages"],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    try:
        request = AgentLoopRequest(
            goal=payload.goal,
            retrieved_context=evidence,
            prefer_local=payload.provider_mode == "local",
            max_turns=payload.max_turns,
            max_output_tokens=payload.max_output_tokens,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Agent input exceeds the supported bounds") from exc

    result = AgentOrchestrator(model_router, build_tool_registry()).run(request)
    run_id = str(uuid4())
    tasks = TaskRepository(settings.database_path)
    tasks.initialize()
    outcome = "success" if result.get("status") == "completed" else "failure"
    AuditLogger(tasks).record(
        event_type="agent.model_run",
        outcome=outcome,
        subject_type="agent_run",
        subject_id=run_id,
        actor_type="user",
        actor_id=user.user_id,
        metadata={
            "provider_mode": payload.provider_mode,
            "status": result.get("status"),
            "selected_provider": (result.get("selected_provider") or {}).get("provider")
            if isinstance(result.get("selected_provider"), dict)
            else None,
            "turns": result.get("turns"),
            "tool_calls": result.get("tool_calls"),
            "context_passage_count": context.get("passage_count", 0),
        },
    )
    context_sources = [
        {
            key: passage.get(key)
            for key in (
                "reference",
                "source_ref",
                "trust_classification",
                "freshness_status",
                "freshness_checked_at",
                "document_hash",
                "chunk_hash",
            )
            if passage.get(key) is not None
        }
        for passage in context["passages"]
    ]
    return {
        "run_id": run_id,
        "provider_mode": payload.provider_mode,
        "context_passage_count": context["passage_count"],
        "context_sources": context_sources,
        "execution": result,
        "external_side_effects_performed": False,
    }
