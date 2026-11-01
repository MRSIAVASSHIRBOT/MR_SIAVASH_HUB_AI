"""Authenticated agent planning API."""

import hashlib
import json
import sqlite3
from typing import Annotated, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from mrhub.agents.core import AgentCore, AgentPlanRequest
from mrhub.agents.repository import AgentRunRepository
from mrhub.agents.workflow_repository import AgentWorkflowRepository
from mrhub.agents.workflow_runner import AgentWorkflowRunner
from mrhub.api.dependencies import require_user
from mrhub.api.routes.models import build_model_router
from mrhub.config import get_settings
from mrhub.domain.tasks import TaskRecord
from mrhub.infrastructure.database import TaskRepository
from mrhub.jobs.idempotency import IdempotencyError, IdempotencyRepository
from mrhub.jobs.payload_envelope import PayloadEnvelopeError, encrypt_payload, load_payload_key
from mrhub.jobs.recovery import WorkflowRecoveryRepository
from mrhub.security.audit import AuditLogger
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
    """Validate and durably enqueue a workflow; execution belongs to WorkerEngine."""
    core = AgentCore(build_model_router(), build_tool_registry())
    try:
        plan = core.plan(request)
        request_digest = _workflow_digest(request)
        settings = get_settings()
        if not plan.get("execution_ready"):
            legacy = AgentWorkflowRepository(settings.database_path)
            workflow = legacy.create(request_digest, plan, owner_user_id=current_user.user_id)
            return {"workflow": workflow, "execution": None}

        tasks = TaskRepository(settings.database_path)
        tasks.initialize()
        recovery = WorkflowRecoveryRepository(settings.database_path)
        idempotency = IdempotencyRepository(settings.database_path)
        scope = f"agent-workflow:{current_user.user_id}"
        task = TaskRecord(
            task_type="agent.workflow",
            description="Agent workflow execution",
        )
        workflow_id = uuid4()
        try:
            encrypted = encrypt_payload(
                request.model_dump(mode="json"),
                workflow_id=str(workflow_id),
                task_id=str(task.task_id),
                owner_user_id=current_user.user_id,
                key=load_payload_key(),
            )
        except PayloadEnvelopeError as exc:
            raise HTTPException(
                status_code=503,
                detail="Workflow execution is disabled until a valid payload key is configured",
            ) from exc

        idempotency_binding = None
        if idempotency_key is not None:
            try:
                existing_record = idempotency.get(scope, idempotency_key)
            except IdempotencyError as exc:
                raise HTTPException(status_code=422, detail="Invalid idempotency key") from exc
            if existing_record is not None:
                if existing_record.request_digest != request_digest:
                    raise HTTPException(
                        status_code=409,
                        detail="Idempotency key conflicts with an earlier request",
                    )
                if existing_record.workflow_id:
                    existing = recovery.get_run(
                        UUID(existing_record.workflow_id), owner_user_id=current_user.user_id
                    )
                    if existing is not None:
                        return {
                            "workflow": existing,
                            "execution": None,
                            "idempotent_replay": True,
                        }
                raise HTTPException(
                    status_code=409,
                    detail="Request is already being created or requires recovery",
                )
            idempotency_binding = {"scope": scope, "key": idempotency_key}

        step_specs = []
        raw_steps = plan.get("steps", [])
        if not isinstance(raw_steps, list) or not raw_steps:
            raise HTTPException(status_code=422, detail="Workflow plan contains no executable steps")
        for step in raw_steps:
            if not isinstance(step, dict):
                continue
            number = int(step["step"])
            if number == 1:
                kind, name = "provider_selection", "provider_selection"
            else:
                tool = request.tools[number - 2]
                definition = core.tool_registry.get(tool.name)
                kind = "external_tool" if definition.external_side_effect else "safe_tool"
                name = tool.name
            step_specs.append({"step_number": number, "kind": kind, "name": name})

        try:
            recovery.create_run(
                request_digest,
                step_specs,
                task=task,
                owner_user_id=current_user.user_id,
                workflow_id=workflow_id,
                payload_envelope={
                    "version": encrypted.version,
                    "nonce_b64": encrypted.nonce_b64,
                    "ciphertext_b64": encrypted.ciphertext_b64,
                },
                idempotency_binding=idempotency_binding,
            )
        except sqlite3.IntegrityError as exc:
            if idempotency_key is not None:
                record = idempotency.get(scope, idempotency_key)
                if record is not None and record.request_digest == request_digest and record.workflow_id:
                    existing = recovery.get_run(
                        UUID(record.workflow_id), owner_user_id=current_user.user_id
                    )
                    if existing is not None:
                        return {
                            "workflow": existing,
                            "execution": None,
                            "idempotent_replay": True,
                        }
            raise HTTPException(
                status_code=409,
                detail="Workflow submission conflicts with an existing resource",
            ) from exc
        AuditLogger(tasks).record(
            event_type="task.submitted",
            outcome="queued",
            subject_id=str(task.task_id),
            metadata={
                "task_type": task.task_type,
                "risk_class": task.risk_class.value,
                "decision": "allow",
            },
        )
        return {
            "workflow": recovery.get_run(workflow_id, owner_user_id=current_user.user_id),
            "execution": None,
            "queued": True,
        }
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


@router.post("/workflows/{workflow_id}/cancel")
def cancel_agent_workflow(
    workflow_id: UUID,
    current_user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> dict[str, str]:
    """Request owner-scoped cancellation; running tools finish their current step."""
    settings = get_settings()
    tasks = TaskRepository(settings.database_path)
    tasks.initialize()
    recovery = WorkflowRecoveryRepository(settings.database_path)
    try:
        return recovery.request_cancellation(
            workflow_id, owner_user_id=current_user.user_id
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="Agent workflow not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail="Workflow cannot be cancelled") from exc
    except RuntimeError as exc:
        # WorkflowRecoveryError derives from RuntimeError, not ValueError.
        # Keep invalid-state failures inside the API contract instead of leaking 500s.
        raise HTTPException(status_code=409, detail="Workflow cannot be cancelled") from exc


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
