"""Authenticated agent planning API."""

import hashlib
import json
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from mrhub.agents.core import AgentCore, AgentPlanRequest
from mrhub.agents.repository import AgentRunRepository
from mrhub.agents.workflow_repository import AgentWorkflowRepository
from mrhub.agents.workflow_runner import AgentWorkflowRunner
from mrhub.api.dependencies import require_user
from mrhub.api.routes.models import build_model_router
from mrhub.config import get_settings
from mrhub.infrastructure.database import TaskRepository
from mrhub.jobs.idempotency import IdempotencyConflict, IdempotencyError, IdempotencyRepository
from mrhub.jobs.recovery import WorkflowRecoveryRepository
from mrhub.security.auth import AuthenticatedUser
from mrhub.tools.builtins import build_tool_registry

router = APIRouter(prefix="/agent", tags=["agent"], dependencies=[Depends(require_user)])


class WorkflowReconciliationRequest(BaseModel):
    step_number: int = Field(ge=1)
    outcome: Literal["succeeded", "failed"]
    output_digest: str | None = Field(default=None, pattern="^[0-9a-f]{64}$")


class WorkflowResumeCheckRequest(BaseModel):
    request: AgentPlanRequest


@router.post("/plan")
def create_agent_plan(request: AgentPlanRequest) -> dict[str, object]:
    core = AgentCore(build_model_router(), build_tool_registry())
    try:
        return core.plan(request)
    except LookupError as exc:
        raise HTTPException(
            status_code=503,
            detail="No registered provider satisfies the requested capabilities",
        ) from exc

@router.post("/execute")
def execute_agent_tools(request: AgentPlanRequest, current_user: Annotated[AuthenticatedUser, Depends(require_user)]) -> dict[str, object]:
    """Run only explicitly requested tools that pass the server policy checks."""
    core = AgentCore(build_model_router(), build_tool_registry())
    try:
        execution = core.execute(request)
        repository = AgentRunRepository(get_settings().database_path)
        run = repository.record(request.model_dump(mode="json"), execution, owner_user_id=current_user.user_id)
        return {**execution, "run": run}
    except LookupError as exc:
        raise HTTPException(
            status_code=503,
            detail="No registered provider satisfies the requested capabilities",
        ) from exc

@router.get("/runs/{run_id}")
def get_agent_run(run_id: UUID, current_user: Annotated[AuthenticatedUser, Depends(require_user)]) -> dict[str, object]:
    repository = AgentRunRepository(get_settings().database_path)
    repository.initialize()
    run = repository.get(run_id, owner_user_id=current_user.user_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Agent run not found")
    return run



def _workflow_digest(request: AgentPlanRequest) -> str:
    """Fingerprint the complete in-memory request without persisting its contents."""
    encoded = json.dumps(
        request.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


@router.post("/workflows")
def execute_agent_workflow(
    request: AgentPlanRequest,
    current_user: Annotated[AuthenticatedUser, Depends(require_user)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key", min_length=1, max_length=255)] = None,
) -> dict[str, object]:
    """Execute an allowed workflow under the canonical Job lifecycle."""
    core = AgentCore(build_model_router(), build_tool_registry())
    try:
        plan = core.plan(request)
        request_digest = _workflow_digest(request)
        if not plan["execution_ready"]:
            # Preserve legacy blocked-workflow history without creating an executable job.
            legacy = AgentWorkflowRepository(get_settings().database_path)
            workflow = legacy.create(request_digest, plan, owner_user_id=current_user.user_id)
            return {"workflow": workflow, "execution": None}

        settings = get_settings()
        task_repository = TaskRepository(settings.database_path)
        task_repository.initialize()
        idempotency = IdempotencyRepository(settings.database_path)
        scope = f"agent-workflow:{current_user.user_id}"
        if idempotency_key is not None:
            try:
                reservation = idempotency.reserve(scope, idempotency_key, request_digest)
            except IdempotencyConflict as exc:
                raise HTTPException(status_code=409, detail="Idempotency key conflicts with an earlier request") from exc
            except IdempotencyError as exc:
                raise HTTPException(status_code=422, detail="Invalid idempotency key") from exc
            if not reservation.created:
                record = reservation.record
                if record.workflow_id:
                    existing = WorkflowRecoveryRepository(settings.database_path).get_run(
                        UUID(record.workflow_id), owner_user_id=current_user.user_id
                    )
                    if existing is not None:
                        return {"workflow": existing, "execution": None, "idempotent_replay": True}
                # A reservation without a recoverable workflow may represent a crash
                # between reservation and durable workflow creation. Never replay it.
                raise HTTPException(status_code=409, detail="Request is already reserved; inspect recovery state")
            idempotency.transition(scope, idempotency_key, "accepted", "running")
        try:
            result = AgentWorkflowRunner(task_repository, core).execute(
                request, plan, request_digest, current_user.user_id
            )
        except Exception:
            if idempotency_key is not None:
                try:
                    idempotency.transition(scope, idempotency_key, "running", "unknown_outcome")
                except (RuntimeError, IdempotencyError):
                    pass
            raise
        if idempotency_key is not None:
            workflow = result.get("workflow", {})
            workflow_id = workflow.get("workflow_id") if isinstance(workflow, dict) else None
            task_id = workflow.get("task_id") if isinstance(workflow, dict) else None
            if workflow_id:
                idempotency.bind(scope, idempotency_key, task_id=task_id, workflow_id=workflow_id)
            target = "completed" if result.get("execution", {}).get("execution_completed") else "failed"
            idempotency.transition(scope, idempotency_key, "running", target)
        return result
    except LookupError as exc:
        raise HTTPException(
            status_code=503,
            detail="No registered provider satisfies the requested capabilities",
        ) from exc


@router.get("/workflows/{workflow_id}")
def get_agent_workflow(
    workflow_id: UUID,
    current_user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> dict[str, object]:
    settings = get_settings()
    task_repository = TaskRepository(settings.database_path)
    task_repository.initialize()
    workflow = WorkflowRecoveryRepository(task_repository.database_path).get_run(
        workflow_id, owner_user_id=current_user.user_id
    )
    if workflow is not None:
        return workflow

    # Read legacy workflow rows created before the unified Job/Workflow migration.
    legacy = AgentWorkflowRepository(settings.database_path)
    legacy.initialize()
    workflow = legacy.get(workflow_id, owner_user_id=current_user.user_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail="Agent workflow not found")
    return workflow


@router.post("/workflows/{workflow_id}/reconciliation")
def reconcile_agent_workflow(
    workflow_id: UUID,
    request: WorkflowReconciliationRequest,
    current_user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> dict[str, object]:
    """Record an externally verified outcome; this endpoint never executes a tool."""
    settings = get_settings()
    tasks = TaskRepository(settings.database_path)
    tasks.initialize()
    recovery = WorkflowRecoveryRepository(settings.database_path)
    try:
        checkpoint = recovery.resolve_unknown_step(
            workflow_id,
            request.step_number,
            request.outcome,
            output_digest=request.output_digest,
            owner_user_id=current_user.user_id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="Workflow not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Invalid reconciliation request") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail="Workflow cannot be reconciled in its current state") from exc
    return {
        "workflow": recovery.get_run(workflow_id, owner_user_id=current_user.user_id),
        "checkpoint": checkpoint.__dict__ if checkpoint is not None else None,
        "execution_started": False,
    }


@router.post("/workflows/{workflow_id}/resume-check")
def check_agent_workflow_resume(
    workflow_id: UUID,
    request: WorkflowResumeCheckRequest,
    current_user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> dict[str, object]:
    """Validate supplied original inputs and return a decision without replaying work."""
    settings = get_settings()
    tasks = TaskRepository(settings.database_path)
    tasks.initialize()
    recovery = WorkflowRecoveryRepository(settings.database_path)
    try:
        decision = recovery.resume_decision(
            workflow_id,
            _workflow_digest(request.request),
            owner_user_id=current_user.user_id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="Workflow not found") from exc
    return {
        "workflow_id": str(workflow_id),
        "decision": decision.decision,
        "next_step": decision.next_step,
        "checkpoint_version": decision.checkpoint_version,
        "reason_code": decision.reason_code,
        "execution_started": False,
        "note": "This endpoint evaluates resumability only; it does not execute or replay steps.",
    }



@router.post("/workflows/{workflow_id}/resume")
def resume_agent_workflow(
    workflow_id: UUID,
    request: WorkflowResumeCheckRequest,
    current_user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> dict[str, object]:
    """Resume an owned workflow only after re-planning and validating original inputs."""
    settings = get_settings()
    tasks = TaskRepository(settings.database_path)
    tasks.initialize()
    core = AgentCore(build_model_router(), build_tool_registry())
    try:
        plan = core.plan(request.request)
        return AgentWorkflowRunner(tasks, core).resume(
            workflow_id,
            request.request,
            plan,
            _workflow_digest(request.request),
            current_user.user_id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="Workflow not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail="Workflow is not safely resumable") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail="Workflow resume could not be completed") from exc
