"""Authenticated owner-scoped specialist-agent proposal lifecycle."""

from __future__ import annotations

import hashlib
import json
from typing import Annotated, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from mrhub.agents.proposals import AgentProposal, validate_agent_proposal
from mrhub.agents.registry import build_default_agent_registry
from mrhub.agents.proposal_repository import AgentProposalRepository
from mrhub.api.dependencies import require_user
from mrhub.config import get_settings
from mrhub.infrastructure.database import TaskRepository
from mrhub.security.audit import AuditLogger
from mrhub.security.auth import AuthenticatedUser
from mrhub.tools.builtins import build_tool_registry

router = APIRouter(
    prefix="/agent/proposals",
    tags=["agent-proposals"],
    dependencies=[Depends(require_user)],
)


class ProposalReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    decision: Literal["approved", "rejected"]


def _fingerprint(proposal_id: UUID, payload: AgentProposal) -> str:
    canonical = json.dumps(
        {
            "proposal_id": str(proposal_id),
            "proposal": payload.model_dump(mode="json"),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _repository() -> AgentProposalRepository:
    return AgentProposalRepository(get_settings().database_path)


def _validate(payload: AgentProposal) -> None:
    tools = build_tool_registry()
    agents = build_default_agent_registry(tools)
    validate_agent_proposal(payload, agents=agents, tools=tools)


@router.post("", status_code=201)
def create_agent_proposal(
    payload: AgentProposal,
    user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> dict[str, object]:
    try:
        _validate(payload)
        proposal_id = uuid4()
        fingerprint = _fingerprint(proposal_id, payload)
        record = _repository().create(
            proposal_id,
            user.user_id,
            payload.model_dump(mode="json"),
            fingerprint,
        )
    except (ValueError, LookupError) as exc:
        raise HTTPException(status_code=422, detail="Agent proposal failed validation") from exc

    AuditLogger(TaskRepository(get_settings().database_path)).record(
        event_type="agent.proposal_created",
        outcome="pending_review",
        subject_type="agent_proposal",
        subject_id=str(proposal_id),
        actor_type="user",
        actor_id=user.user_id,
    )
    return record


@router.get("")
def list_agent_proposals(
    user: Annotated[AuthenticatedUser, Depends(require_user)],
    limit: int = Query(default=50, ge=1, le=100),
) -> dict[str, object]:
    records = _repository().list(owner_user_id=user.user_id, limit=limit)
    return {"proposals": records, "count": len(records)}


@router.get("/{proposal_id}")
def get_agent_proposal(
    proposal_id: UUID,
    user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> dict[str, object]:
    record = _repository().get(proposal_id, owner_user_id=user.user_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Agent proposal not found")
    return record


@router.post("/{proposal_id}/review")
def review_agent_proposal(
    proposal_id: UUID,
    payload: ProposalReviewRequest,
    user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> dict[str, object]:
    repository = _repository()
    record = repository.get(proposal_id, owner_user_id=user.user_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Agent proposal not found")
    try:
        proposal = AgentProposal.model_validate(
            {key: record[key] for key in (
                "name", "description", "instructions", "allowed_tools",
                "max_turns", "rationale",
            )}
        )
        expected_fingerprint = _fingerprint(proposal_id, proposal)
        if expected_fingerprint != record["fingerprint"] or payload.fingerprint != expected_fingerprint:
            raise HTTPException(status_code=409, detail="Proposal fingerprint is stale")
        if payload.decision == "approved":
            # Revalidate against current registries; approval is not activation.
            _validate(proposal)
    except (ValueError, LookupError) as exc:
        raise HTTPException(status_code=409, detail="Proposal is no longer valid") from exc

    reviewed = repository.review(
        proposal_id,
        owner_user_id=user.user_id,
        fingerprint=expected_fingerprint,
        decision=payload.decision,
    )
    if reviewed is None:
        raise HTTPException(status_code=409, detail="Proposal was already reviewed or changed")

    AuditLogger(TaskRepository(get_settings().database_path)).record(
        event_type="agent.proposal_reviewed",
        outcome=payload.decision,
        subject_type="agent_proposal",
        subject_id=str(proposal_id),
        actor_type="user",
        actor_id=user.user_id,
    )
    return reviewed
