"""Authenticated, non-applying NEXUS patch proposal and diff review API."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from mrhub.api.dependencies import require_user
from mrhub.config import get_settings
from mrhub.infrastructure.database import TaskRepository
from mrhub.nexus.patch_proposals import PatchProposalError, create_patch_proposal
from mrhub.security.audit import AuditLogger
from mrhub.security.auth import AuthenticatedUser

router = APIRouter(
    prefix="/nexus",
    tags=["nexus"],
    dependencies=[Depends(require_user)],
)


class PatchProposalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = Field(min_length=1, max_length=200)
    original_source: str = Field(max_length=64_000)
    proposed_source: str = Field(max_length=64_000)


@router.post("/patch-proposals")
def propose_patch(
    request: PatchProposalRequest,
    current_user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> dict[str, object]:
    """Create a review-only diff; no repository file is read, written, or executed."""
    try:
        proposal = create_patch_proposal(
            request.path,
            request.original_source,
            request.proposed_source,
        )
    except PatchProposalError as exc:
        reason = str(exc)
        status = 413 if reason in {"source_too_large", "diff_too_large"} else 422
        raise HTTPException(
            status_code=status,
            detail={"reason_code": reason},
        ) from exc

    repository = TaskRepository(get_settings().database_path)
    repository.initialize()
    AuditLogger(repository).record(
        event_type="nexus.patch_proposal_generated",
        outcome="success",
        subject_type="nexus_patch_proposal",
        subject_id=str(proposal["proposal_id"]),
        actor_type="user",
        actor_id=current_user.user_id,
        metadata={"reason_code": "patch_proposal_generated", "decision": "allow"},
    )
    return proposal
