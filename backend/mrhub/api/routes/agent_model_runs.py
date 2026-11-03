"""Queued, owner-scoped model-driven Agent run API."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException

from mrhub.agents.context import AgentContextAssembler
from mrhub.agents.orchestrator import AgentLoopRequest
from mrhub.api.dependencies import require_user
from mrhub.api.routes.agent_run import AgentRunRequest
from mrhub.api.routes.models import build_model_router
from mrhub.config import get_settings
from mrhub.domain.tasks import TaskRecord
from mrhub.infrastructure.database import TaskRepository
from mrhub.jobs.idempotency import IdempotencyConflict, IdempotencyRepository
from mrhub.jobs.payload_envelope import (
    EncryptedPayload,
    PayloadEnvelopeError,
    decrypt_payload,
    encrypt_payload,
    load_payload_key,
)
from mrhub.jobs.recovery import WorkflowRecoveryError, WorkflowRecoveryRepository
from mrhub.providers.router import ModelRequest
from mrhub.security.auth import AuthenticatedUser

router = APIRouter(prefix="/agent", tags=["agent"], dependencies=[Depends(require_user)])


def _repositories() -> tuple[TaskRepository, WorkflowRecoveryRepository]:
    repository = TaskRepository(get_settings().database_path)
    repository.initialize()
    return repository, WorkflowRecoveryRepository(repository.database_path)


def _digest(value: object) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@router.post("/model-runs", status_code=202)
def submit_model_run(
    payload: AgentRunRequest,
    user: Annotated[AuthenticatedUser, Depends(require_user)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=255)],
) -> dict[str, object]:
    """Queue one bounded model-driven run; the HTTP request never executes inference."""
    settings = get_settings()
    scope = f"agent.model_run:{user.user_id}"
    request_data = payload.model_dump(mode="json")
    request_digest = _digest(request_data)
    idempotency = IdempotencyRepository(settings.database_path)
    existing = idempotency.get(scope, idempotency_key)
    if existing is not None:
        if existing.request_digest != request_digest:
            raise HTTPException(
                status_code=409, detail="Idempotency key was used for another request"
            )
        if existing.workflow_id:
            return {
                "workflow_id": existing.workflow_id,
                "task_id": existing.task_id,
                "status": existing.status,
                "idempotent_replay": True,
            }
        raise HTTPException(status_code=409, detail="Idempotency key is already reserved")

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
        load_payload_key()
    except (LookupError, PayloadEnvelopeError) as exc:
        raise HTTPException(
            status_code=503,
            detail="Requested inference provider or encrypted workflow storage is unavailable",
        ) from exc

    query = (payload.context_query or payload.goal)[:200]
    context_options: dict[str, object] = {
        "query": query,
        "include_memory": payload.include_memory,
        "include_knowledge": payload.include_knowledge,
    }
    freshness_policy = getattr(payload, "knowledge_freshness_policy", None)
    if freshness_policy is not None:
        context_options["knowledge_freshness_policy"] = freshness_policy
    context = AgentContextAssembler(settings.database_path).assemble(
        user.user_id, **context_options
    )
    evidence = json.dumps(
        context["passages"], ensure_ascii=False, separators=(",", ":")
    )
    try:
        AgentLoopRequest(
            goal=payload.goal,
            retrieved_context=evidence,
            prefer_local=payload.provider_mode == "local",
            max_turns=payload.max_turns,
            max_output_tokens=payload.max_output_tokens,
            max_runtime_seconds=payload.max_runtime_seconds,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=422, detail="Agent input exceeds the supported bounds"
        ) from exc
    context_sources = [
        {
            key: passage.get(key)
            for key in (
                "reference", "source_ref", "trust_classification",
                "freshness_status", "freshness_checked_at",
                "freshness_review_expired", "freshness_review_max_age_days",
                "content_integrity_verified", "document_hash", "chunk_hash",
            )
            if passage.get(key) is not None
        }
        for passage in context["passages"]
    ]

    workflow_id = uuid4()
    task = TaskRecord(
        task_type="agent.model_run",
        description="Queued bounded model-driven Agent run",
    )
    encrypted = encrypt_payload(
        {
            "kind": "agent.model_run.request",
            "request": request_data,
            "evidence": evidence,
            "context_sources": context_sources,
            "context_summary": {
                "passage_count": context.get("passage_count", 0),
                "knowledge_freshness_policy": context.get(
                    "knowledge_freshness_policy", "include_all"
                ),
                "excluded_stale_knowledge_count": context.get("excluded_stale_knowledge_count", 0),
                "excluded_unreviewed_knowledge_count": context.get(
                    "excluded_unreviewed_knowledge_count", 0
                ),
                "excluded_expired_knowledge_count": context.get(
                    "excluded_expired_knowledge_count", 0
                ),
                "freshness_review_max_age_days": context.get(
                    "freshness_review_max_age_days", 30
                ),
            },
        },
        workflow_id=str(workflow_id),
        task_id=str(task.task_id),
        owner_user_id=user.user_id,
        key=load_payload_key(),
    )
    try:
        recovery = WorkflowRecoveryRepository(settings.database_path)
        recovery.create_run(
            request_digest,
            [{"step_number": 1, "kind": "model_inference",
              "name": "Model-driven Agent execution"}],
            task=task,
            owner_user_id=user.user_id,
            workflow_id=workflow_id,
            payload_envelope={
                "version": encrypted.version,
                "nonce_b64": encrypted.nonce_b64,
                "ciphertext_b64": encrypted.ciphertext_b64,
            },
            idempotency_binding={"scope": scope, "key": idempotency_key},
        )
    except (sqlite3.IntegrityError, IdempotencyConflict) as exc:
        saved = idempotency.get(scope, idempotency_key)
        if saved is not None and saved.request_digest == request_digest and saved.workflow_id:
            return {
                "workflow_id": saved.workflow_id,
                "task_id": saved.task_id,
                "status": saved.status,
                "idempotent_replay": True,
            }
        raise HTTPException(
            status_code=409, detail="Idempotency key conflicts with another run"
        ) from exc

    return {
        "workflow_id": str(workflow_id),
        "task_id": str(task.task_id),
        "status": "queued",
        "idempotent_replay": False,
        "context_passage_count": context.get("passage_count", 0),
        "knowledge_freshness_policy": context.get("knowledge_freshness_policy", "include_all"),
        "excluded_stale_knowledge_count": context.get("excluded_stale_knowledge_count", 0),
        "excluded_unreviewed_knowledge_count": context.get(
            "excluded_unreviewed_knowledge_count", 0
        ),
        "excluded_expired_knowledge_count": context.get(
            "excluded_expired_knowledge_count", 0
        ),
        "freshness_review_max_age_days": context.get(
            "freshness_review_max_age_days", 30
        ),
    }


@router.get("/model-run-workflows/{workflow_id}")
def get_model_run(
    workflow_id: UUID,
    user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> dict[str, object]:
    """Return owner-only workflow metadata and decrypt the result only after success."""
    _repository, recovery = _repositories()
    run = recovery.get_run(workflow_id, owner_user_id=user.user_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Model run not found")
    response: dict[str, object] = {
        "workflow_id": str(workflow_id),
        "task_id": run["task_id"],
        "status": run["status"],
        "current_step": run["current_step"],
        "last_error_code": run["last_error_code"],
        "steps": run["steps"],
        "result": None,
    }
    if run["status"] in {"succeeded", "cancelled"}:
        stored = recovery.get_encrypted_payload(workflow_id, owner_user_id=user.user_id)
        if stored is not None:
            try:
                result = decrypt_payload(
                    EncryptedPayload(
                        version=int(stored["version"]),
                        nonce_b64=str(stored["nonce_b64"]),
                        ciphertext_b64=str(stored["ciphertext_b64"]),
                    ),
                    workflow_id=str(workflow_id),
                    task_id=str(run["task_id"]),
                    owner_user_id=user.user_id,
                    key=load_payload_key(),
                )
                if result.get("kind") == "agent.model_run.result":
                    response["result"] = {
                        "provider_mode": result.get("provider_mode"),
                        "context_sources": result.get("context_sources", []),
                        "context_summary": result.get("context_summary", {}),
                        "execution": result.get("execution"),
                    }
            except (PayloadEnvelopeError, TypeError, ValueError):
                raise HTTPException(
                    status_code=503, detail="Encrypted model-run result is unavailable"
                )
    return response


@router.post("/model-run-workflows/{workflow_id}/cancel")
def cancel_model_run(
    workflow_id: UUID,
    user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> dict[str, str]:
    """Cancel queued work or request cooperative cancellation of a running model loop."""
    _repository, recovery = _repositories()
    try:
        return recovery.request_cancellation(workflow_id, owner_user_id=user.user_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="Model run not found") from exc
    except WorkflowRecoveryError as exc:
        raise HTTPException(
            status_code=409,
            detail="Model run cannot be cancelled in its current state",
        ) from exc
