"""Authenticated bounded model-driven Agent execution with explicit provider mode."""

from __future__ import annotations

import json
from typing import Annotated, Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from mrhub.agents.context import AgentContextAssembler
from mrhub.agents.orchestrator import AgentLoopRequest, AgentOrchestrator
from mrhub.agents.registry import build_default_agent_registry
from mrhub.api.dependencies import require_user
from mrhub.api.routes.models import build_model_router
from mrhub.config import get_settings
from mrhub.infrastructure.database import TaskRepository
from mrhub.jobs.worker_control import WorkerControlRepository
from mrhub.projects.registry import get_project_context
from mrhub.providers.router import ModelRequest
from mrhub.security.audit import AuditLogger
from mrhub.security.auth import AuthenticatedUser
from mrhub.tools.builtins import build_tool_registry

router = APIRouter(prefix="/agent", tags=["agent"], dependencies=[Depends(require_user)])


class AgentRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    goal: str = Field(min_length=1, max_length=1_000)
    project_id: str | None = Field(
        default=None, min_length=1, max_length=64,
        pattern=r"^[a-z0-9][a-z0-9-]{0,63}$",
    )
    context_query: str | None = Field(default=None, min_length=1, max_length=200)
    provider_mode: Literal["local", "remote"] = "local"
    include_memory: bool = True
    include_knowledge: bool = True
    knowledge_freshness_policy: Literal[
        "include_all", "owner_reviewed_current_only"
    ] = "include_all"
    max_turns: int = Field(default=3, ge=1, le=3)
    max_output_tokens: int = Field(default=512, ge=1, le=512)
    max_runtime_seconds: int = Field(default=30, ge=1, le=30)


@router.post("/run")
def run_agent(
    payload: AgentRunRequest,
    user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> dict[str, object]:
    """Run one explicitly bounded model loop; no stub or provider fallback is permitted."""
    settings = get_settings()
    selected_project = None
    if payload.project_id is not None:
        selected_project = get_project_context(payload.project_id)
        if selected_project is None:
            raise HTTPException(status_code=404, detail="Project is not enrolled")

    model_router = build_model_router(
        provider_mode=payload.provider_mode,
        include_stub=False,
        max_timeout_seconds=30.0,
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
        knowledge_freshness_policy=payload.knowledge_freshness_policy,
    )
    evidence_payload: object = context["passages"]
    if selected_project is not None:
        evidence_payload = {
            "memory_knowledge_passages": context["passages"],
            "selected_project_context": selected_project,
            "project_context_is_untrusted_data": True,
        }
    evidence = json.dumps(
        evidence_payload,
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
            max_runtime_seconds=payload.max_runtime_seconds,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Agent input exceeds the supported bounds") from exc

    worker_control = WorkerControlRepository(settings.database_path)
    tool_registry = build_tool_registry()
    agent_registry = build_default_agent_registry(tool_registry)
    result = AgentOrchestrator(model_router, tool_registry, agent_registry).run(
        request,
        should_cancel=worker_control.is_stopped,
    )
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
            **({"project_id": payload.project_id} if payload.project_id else {}),
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
                "freshness_review_expired",
                "freshness_review_max_age_days",
                "content_integrity_verified",
                "document_hash",
                "chunk_hash",
            )
            if passage.get(key) is not None
        }
        for passage in context["passages"]
    ]
    if selected_project is not None:
        context_sources.append({
            "reference": selected_project["reference"],
            "trust_classification": selected_project["trust_classification"],
        })
    return {
        "run_id": run_id,
        "project_context": (
            {
                "project_id": payload.project_id,
                "reference": selected_project["reference"],
                "included": True,
            }
            if selected_project is not None
            else None
        ),
        "provider_mode": payload.provider_mode,
        "context_passage_count": context["passage_count"],
        "knowledge_freshness_policy": context["knowledge_freshness_policy"],
        "excluded_stale_knowledge_count": context["excluded_stale_knowledge_count"],
        "excluded_unreviewed_knowledge_count": context["excluded_unreviewed_knowledge_count"],
        "excluded_expired_knowledge_count": context["excluded_expired_knowledge_count"],
        "freshness_review_max_age_days": context["freshness_review_max_age_days"],
        "context_sources": context_sources,
        "execution": result,
        "external_side_effects_performed": False,
    }


@router.get("/model-runs")
def list_model_runs(
    user: Annotated[AuthenticatedUser, Depends(require_user)],
    limit: int = Query(default=20, ge=1, le=100),
) -> dict[str, object]:
    """List recent metadata-only model runs for the authenticated owner."""
    tasks = TaskRepository(get_settings().database_path)
    tasks.initialize()
    runs = tasks.list_agent_model_runs(user.user_id, limit=limit)
    return {"runs": runs, "count": len(runs)}


@router.get("/model-runs/{run_id}")
def get_model_run(
    run_id: str,
    user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> dict[str, object]:
    """Retrieve one model-run record without exposing prompts or generated content."""
    tasks = TaskRepository(get_settings().database_path)
    tasks.initialize()
    run = tasks.get_agent_model_run(user.user_id, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Agent model run not found")
    return run
