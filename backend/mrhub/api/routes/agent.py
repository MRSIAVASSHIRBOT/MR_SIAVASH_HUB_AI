"""Authenticated agent planning API."""

import hashlib
import hmac
import json
import sqlite3
from typing import Annotated, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator

from mrhub.agents.awi_planner import ExecutionPlan, PlanningError, generate_execution_plan
from mrhub.agents.core import AgentCore, AgentPlanRequest, AgentToolRequest
from mrhub.agents.plan_execution import (
    PLAN_EXECUTION_FORMAT,
    PlanExecutionBindingError,
    execution_request_digest,
    topological_plan_steps,
    tool_contract_digest,
)
from mrhub.agents.gpi import (
    WorkOrderGenerationError,
    derive_server_risk_class,
    generate_work_order,
)
from mrhub.agents.plan_repository import (
    AgentWorkOrderPlanError,
    AgentWorkOrderPlanRepository,
)
from mrhub.agents.registry import build_default_agent_registry
from mrhub.agents.repository import AgentRunRepository
from mrhub.agents.work_order import WorkOrder, assess_work_order_capabilities
from mrhub.agents.workflow_repository import AgentWorkflowRepository
from mrhub.agents.workflow_runner import AgentWorkflowRunner
from mrhub.api.dependencies import require_user
from mrhub.api.routes.models import _enforce_kimi_request_limit, build_model_router
from mrhub.capabilities.registry import CapabilityRegistry
from mrhub.config import get_settings
from mrhub.domain.tasks import RiskClass, TaskRecord
from mrhub.infrastructure.database import TaskRepository
from mrhub.integrations.health_probe import INTEGRATION_CONTRACT_VERSION
from mrhub.jobs.idempotency import (
    IdempotencyConflict,
    IdempotencyError,
    IdempotencyRepository,
)
from mrhub.jobs.payload_envelope import (
    PayloadEnvelopeError,
    decrypt_plan_payload,
    encrypt_payload,
    encrypt_plan_payload,
    load_payload_key,
)
from mrhub.jobs.recovery import WorkflowRecoveryError, WorkflowRecoveryRepository
from mrhub.providers.base import ProviderError
from mrhub.providers.router import ModelRequest
from mrhub.security.audit import AuditLogger
from mrhub.security.auth import AuthenticatedUser
from mrhub.security.tool_permissions import ToolPermissionService
from mrhub.tools.builtins import build_tool_registry

router = APIRouter(prefix="/agent", tags=["agent"], dependencies=[Depends(require_user)])


def _build_owner_agent_core(
    owner_user_id: str,
    repository: TaskRepository | None = None,
) -> AgentCore:
    """Build an AgentCore whose grants come only from the authenticated owner store."""
    tasks = repository or TaskRepository(get_settings().database_path)
    tasks.initialize()
    permissions = ToolPermissionService(tasks, AuditLogger(tasks))
    return AgentCore(
        build_model_router(),
        build_tool_registry(owner_user_id=owner_user_id),
        permission_provider=lambda: permissions.active_permissions(owner_user_id),
    )


class WorkflowReconciliationRequest(BaseModel):
    step_number: int = Field(ge=1)
    outcome: Literal["succeeded", "failed"]
    output_digest: str | None = Field(default=None, pattern="^[0-9a-f]{64}$")


class WorkflowResumeCheckRequest(BaseModel):
    request: AgentPlanRequest


class GoalPlanningRequest(BaseModel):
    """Bounded natural-language goal submitted for planning only."""

    model_config = ConfigDict(extra="forbid")

    goal: str = Field(min_length=1, max_length=1_000)

    @field_validator("goal")
    @classmethod
    def normalize_goal(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("goal must not be blank")
        return normalized


class PersistedGoalPlanningRequest(GoalPlanningRequest):
    """Bounded request for a short-lived, encrypted plan record."""

    expires_in_seconds: int = Field(default=900, ge=60, le=86_400)


class PersistedPlanStepBinding(BaseModel):
    """Explicit user-supplied mapping from one AWI step to one typed tool payload."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    step_id: str = Field(min_length=1, max_length=40, pattern=r"^[a-z][a-z0-9_-]{0,39}$")
    tool_name: str = Field(min_length=1, max_length=80, pattern=r"^[a-z][a-z0-9_.-]{0,79}$")
    payload: dict[str, object] = Field(default_factory=dict)

    @field_validator("payload")
    @classmethod
    def bound_payload_size(cls, value: dict[str, object]) -> dict[str, object]:
        """Reject non-JSON values and oversized tool arguments before planning."""
        try:
            encoded = json.dumps(
                value,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise ValueError("tool payload must contain finite JSON values") from exc
        if len(encoded) > 16_384:
            raise ValueError("tool payload exceeds the 16 KiB limit")
        return value


class ExecutePersistedPlanRequest(BaseModel):
    """Exact plan digest and one explicit tool binding per executable step."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    plan_digest: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    bindings: list[PersistedPlanStepBinding] = Field(min_length=1, max_length=5)


def _canonical_plan_digest(payload: dict[str, object]) -> str:
    """Fingerprint canonical JSON without writing plan content to plaintext storage."""
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@router.post("/work-orders/plan")
def create_goal_work_order_plan(
    request: GoalPlanningRequest,
    current_user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> dict[str, object]:
    """Convert a goal into a validated plan without executing tools."""
    tasks = TaskRepository(get_settings().database_path)
    tasks.initialize()
    audit_logger = AuditLogger(tasks)

    # Reject prohibited intent before provider selection, inference, or quota use.
    # Persist a minimal denial event without storing the raw goal or prompt.
    if derive_server_risk_class(request.goal, {}) is RiskClass.PROHIBITED:
        try:
            audit_logger.record(
                event_type="agent.work_order_blocked",
                outcome="denied",
                actor_type="user",
                actor_id=current_user.user_id,
                subject_type="work_order",
                metadata={
                    "status": "blocked",
                    "declared_risk_class": RiskClass.PROHIBITED.value,
                    "declared_risk_is_authoritative": False,
                },
            )
        except sqlite3.Error as exc:
            raise HTTPException(
                status_code=503,
                detail="Audit storage is unavailable",
            ) from exc
        raise HTTPException(
            status_code=422,
            detail="The requested goal is outside the supported safety policy",
        )

    # Confirm the audit sink is writable before any provider selection or inference.
    try:
        audit_logger.record(
            event_type="agent.work_order_planning_started",
            outcome="started",
            actor_type="user",
            actor_id=current_user.user_id,
            subject_type="work_order",
            metadata={"status": "planning_started"},
        )
    except sqlite3.Error as exc:
        raise HTTPException(
            status_code=503,
            detail="Audit storage is unavailable",
        ) from exc

    try:
        model_router = build_model_router(include_stub=False, max_timeout_seconds=60)
        selection = model_router.select(ModelRequest(requires_text=True))
        if selection.provider == "moonshot":
            _enforce_kimi_request_limit(current_user.user_id)
        work_order = generate_work_order(request.goal, model_router)
        if work_order.risk_class.value == "prohibited":
            raise HTTPException(
                status_code=422,
                detail="The requested goal is outside the supported safety policy",
            )
        if selection.provider == "moonshot":
            _enforce_kimi_request_limit(current_user.user_id)
        plan = generate_execution_plan(work_order, model_router)
    except (WorkOrderGenerationError, PlanningError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(
            status_code=503,
            detail="No configured non-stub model provider is available",
        ) from exc
    except ProviderError as exc:
        raise HTTPException(status_code=503, detail=exc.code) from exc

    registry = build_tool_registry(owner_user_id=current_user.user_id)
    try:
        assessment = assess_work_order_capabilities(work_order, registry.catalog())
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=503,
            detail="Registered tool catalog is not valid for capability assessment",
        ) from exc

    audit_logger.record(
        event_type="agent.work_order_planned",
        outcome="planned",
        actor_type="user",
        actor_id=current_user.user_id,
        subject_type="work_order",
        metadata={
            "provider_mode": "local" if selection.local else "kimi",
            "selected_provider": selection.provider,
            "status": "planned",
            "required_capability_count": len(assessment.required),
            "available_capability_count": len(assessment.available),
            "missing_capability_count": len(assessment.missing),
            "declared_risk_class": work_order.risk_class.value,
            "declared_risk_is_authoritative": False,
        },
    )
    return {
        "work_order": work_order.model_dump(mode="json"),
        "plan": plan.model_dump(mode="json"),
        "capability_assessment": {
            **assessment.as_dict(),
            "authorization_checked": False,
        },
        "risk_class_is_authoritative": False,
        "planning_only": True,
        "execution_ready": False,
        "execution_started": False,
        "tools_executed": False,
        "permissions_changed": False,
    }


@router.post("/work-orders/plans")
def create_persisted_goal_work_order_plan(
    request: PersistedGoalPlanningRequest,
    current_user: Annotated[AuthenticatedUser, Depends(require_user)],
    response: Response,
) -> dict[str, object]:
    """Create a short-lived encrypted plan record; this endpoint still never executes tools."""
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["Pragma"] = "no-cache"
    response.headers["X-Content-Type-Options"] = "nosniff"
    settings = get_settings()
    tasks = TaskRepository(settings.database_path)
    tasks.initialize()

    # Fail before model inference when durable plan encryption is not configured.
    try:
        key = load_payload_key()
    except PayloadEnvelopeError as exc:
        raise HTTPException(
            status_code=503,
            detail="Persisted plans are disabled until a valid payload key is configured",
        ) from exc

    planned = create_goal_work_order_plan(
        GoalPlanningRequest(goal=request.goal),
        current_user,
    )
    plan_id = str(uuid4())
    payload = {
        "work_order": planned["work_order"],
        "plan": planned["plan"],
    }
    try:
        envelope = encrypt_plan_payload(
            payload,
            plan_id=plan_id,
            owner_user_id=current_user.user_id,
            key=key,
        )
        record = AgentWorkOrderPlanRepository(settings.database_path).create(
            plan_id=plan_id,
            owner_user_id=current_user.user_id,
            plan_digest=_canonical_plan_digest(payload),
            envelope=envelope,
            ttl_seconds=request.expires_in_seconds,
        )
    except PayloadEnvelopeError as exc:
        raise HTTPException(
            status_code=503,
            detail="The generated plan could not be encrypted safely",
        ) from exc
    except sqlite3.Error as exc:
        raise HTTPException(
            status_code=503,
            detail="Encrypted plan storage is unavailable",
        ) from exc
    except AgentWorkOrderPlanError as exc:
        raise HTTPException(status_code=422, detail="The plan record is invalid") from exc

    return {
        "plan_id": record.plan_id,
        "status": record.status,
        "plan_digest": record.plan_digest,
        "created_at": record.created_at,
        "expires_at": record.expires_at,
        "work_order": planned["work_order"],
        "plan": planned["plan"],
        "capability_assessment": planned["capability_assessment"],
        "risk_class_is_authoritative": False,
        "planning_only": True,
        "execution_ready": False,
        "execution_started": False,
        "tools_executed": False,
        "permissions_changed": False,
    }


@router.get("/work-orders/plans/{plan_id}")
def get_persisted_goal_work_order_plan(
    plan_id: UUID,
    current_user: Annotated[AuthenticatedUser, Depends(require_user)],
    response: Response,
) -> dict[str, object]:
    """Read and authenticate one encrypted plan record belonging to the current owner."""
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["Pragma"] = "no-cache"
    response.headers["X-Content-Type-Options"] = "nosniff"
    settings = get_settings()
    TaskRepository(settings.database_path).initialize()
    record = AgentWorkOrderPlanRepository(settings.database_path).get(
        str(plan_id),
        owner_user_id=current_user.user_id,
    )
    if record is None:
        raise HTTPException(status_code=404, detail="Plan record not found")
    if record.status == "expired":
        raise HTTPException(status_code=410, detail="Plan record has expired")
    if record.status != "active":
        raise HTTPException(status_code=409, detail="Plan record is not available")

    try:
        key = load_payload_key()
    except PayloadEnvelopeError as exc:
        raise HTTPException(
            status_code=503,
            detail="Persisted plans are unavailable until a valid payload key is configured",
        ) from exc

    try:
        payload = decrypt_plan_payload(
            record.envelope,
            plan_id=record.plan_id,
            owner_user_id=record.owner_user_id,
            key=key,
        )
        if set(payload) != {"work_order", "plan"}:
            raise PayloadEnvelopeError("Agent plan payload shape is invalid")
        work_order = WorkOrder.model_validate(payload["work_order"])
        plan = ExecutionPlan.model_validate(payload["plan"])
        canonical = {
            "work_order": work_order.model_dump(mode="json"),
            "plan": plan.model_dump(mode="json"),
        }
        digest = _canonical_plan_digest(canonical)
        if not hmac.compare_digest(digest, record.plan_digest):
            raise PayloadEnvelopeError("Agent plan digest does not match its stored record")
    except (PayloadEnvelopeError, ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=409,
            detail="Plan record failed integrity or schema validation",
        ) from exc

    registry = build_tool_registry(owner_user_id=current_user.user_id)
    try:
        assessment = assess_work_order_capabilities(work_order, registry.catalog())
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=503,
            detail="Registered tool catalog is not valid for capability assessment",
        ) from exc

    return {
        "plan_id": record.plan_id,
        "status": record.status,
        "plan_digest": record.plan_digest,
        "created_at": record.created_at,
        "expires_at": record.expires_at,
        "work_order": work_order.model_dump(mode="json"),
        "plan": plan.model_dump(mode="json"),
        "capability_assessment": {
            **assessment.as_dict(),
            "authorization_checked": False,
        },
        "risk_class_is_authoritative": False,
        "planning_only": True,
        "execution_ready": False,
        "execution_started": False,
        "tools_executed": False,
        "permissions_changed": False,
    }


@router.post("/work-orders/plans/{plan_id}/execute")
def execute_persisted_goal_work_order_plan(
    plan_id: UUID,
    request: ExecutePersistedPlanRequest,
    current_user: Annotated[AuthenticatedUser, Depends(require_user)],
    response: Response,
    idempotency_key: Annotated[
        str,
        Header(alias="Idempotency-Key", min_length=1, max_length=255),
    ],
) -> dict[str, object]:
    """Queue a low-risk, explicitly bound plan through the existing durable worker path."""
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["Pragma"] = "no-cache"
    response.headers["X-Content-Type-Options"] = "nosniff"

    settings = get_settings()
    tasks = TaskRepository(settings.database_path)
    tasks.initialize()
    owner_user_id = current_user.user_id
    registry = build_tool_registry(owner_user_id=owner_user_id)

    # Normalize payloads using the live server-owned input schemas. This also
    # makes idempotent replays independent of the plan's now-consumed ciphertext.
    normalized_bindings: list[dict[str, object]] = []
    contract_digests: dict[str, str] = {}
    definitions = {}
    try:
        for binding in request.bindings:
            definition = registry.get(binding.tool_name)
            if (
                definition.risk_class is not RiskClass.LOW
                or definition.external_side_effect
            ):
                raise HTTPException(
                    status_code=403,
                    detail="V1 plan execution only supports low-risk tools without external side effects",
                )
            validated = definition.input_model.model_validate(binding.payload)
            normalized_payload = validated.model_dump(mode="json")
            normalized_bindings.append(
                {
                    "step_id": binding.step_id,
                    "tool_name": binding.tool_name,
                    "payload": normalized_payload,
                }
            )
            contract_digests[binding.tool_name] = tool_contract_digest(definition)
            definitions[binding.tool_name] = definition
    except LookupError as exc:
        raise HTTPException(status_code=422, detail="A bound tool is not registered") from exc
    except (TypeError, ValueError) as exc:
        if isinstance(exc, HTTPException):
            raise
        raise HTTPException(status_code=422, detail="A bound tool payload is invalid") from exc

    try:
        request_digest = execution_request_digest(
            plan_id=str(plan_id),
            plan_digest=request.plan_digest,
            bindings=normalized_bindings,
        )
    except PlanExecutionBindingError as exc:
        raise HTTPException(
            status_code=422,
            detail="Plan execution bindings are not valid finite JSON data",
        ) from exc
    idempotency_scope = f"awi-plan-exec:{owner_user_id}"
    idempotency = IdempotencyRepository(settings.database_path)
    recovery = WorkflowRecoveryRepository(settings.database_path)

    existing = idempotency.get(idempotency_scope, idempotency_key)
    if existing is not None:
        if not hmac.compare_digest(existing.request_digest, request_digest):
            raise HTTPException(
                status_code=409,
                detail="Idempotency key was already used for a different request",
            )
        if not existing.workflow_id:
            raise HTTPException(
                status_code=409,
                detail="The idempotent workflow reservation is incomplete",
            )
        stored_workflow = recovery.get_run(
            UUID(existing.workflow_id),
            owner_user_id=owner_user_id,
        )
        if stored_workflow is None:
            raise HTTPException(status_code=409, detail="The original workflow is unavailable")
        return {
            "workflow": stored_workflow,
            "execution": None,
            "queued": stored_workflow["status"] in {"queued", "running", "paused"},
            "idempotent_replay": True,
            "plan_consumed": True,
            "execution_started": stored_workflow["status"] != "queued",
            "tools_executed": False,
            "permissions_changed": False,
        }

    record = AgentWorkOrderPlanRepository(settings.database_path).get(
        str(plan_id),
        owner_user_id=owner_user_id,
    )
    if record is None:
        raise HTTPException(status_code=404, detail="Plan record not found")
    if record.status == "expired":
        raise HTTPException(status_code=410, detail="Plan record has expired")
    if record.status != "active":
        raise HTTPException(status_code=409, detail="Plan record is not active")
    if not hmac.compare_digest(record.plan_digest, request.plan_digest):
        raise HTTPException(status_code=409, detail="Plan digest does not match the stored plan")

    try:
        key = load_payload_key()
        stored_payload = decrypt_plan_payload(
            record.envelope,
            plan_id=record.plan_id,
            owner_user_id=record.owner_user_id,
            key=key,
        )
        if set(stored_payload) != {"work_order", "plan"}:
            raise PayloadEnvelopeError("Persisted plan payload shape is invalid")
        work_order = WorkOrder.model_validate(stored_payload["work_order"])
        execution_plan = ExecutionPlan.model_validate(stored_payload["plan"])
        canonical_payload = {
            "work_order": work_order.model_dump(mode="json"),
            "plan": execution_plan.model_dump(mode="json"),
        }
        actual_digest = _canonical_plan_digest(canonical_payload)
        if not hmac.compare_digest(actual_digest, record.plan_digest):
            raise PayloadEnvelopeError("Persisted plan digest does not match")
    except PayloadEnvelopeError as exc:
        raise HTTPException(
            status_code=409,
            detail="Persisted plan failed envelope or integrity validation",
        ) from exc
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=409,
            detail="Persisted plan failed schema validation",
        ) from exc

    try:
        ordered_steps = topological_plan_steps(execution_plan)
    except PlanExecutionBindingError as exc:
        raise HTTPException(status_code=409, detail="Plan dependency graph is invalid") from exc
    if len(ordered_steps) != len(request.bindings):
        raise HTTPException(
            status_code=422,
            detail="Every executable plan step must have exactly one explicit tool binding",
        )

    by_step_id = {binding.step_id: binding for binding in request.bindings}
    if len(by_step_id) != len(request.bindings):
        raise HTTPException(status_code=422, detail="Duplicate plan step bindings are not allowed")
    ordered_bindings: list[PersistedPlanStepBinding] = []
    for step in ordered_steps:
        binding = by_step_id.get(step.step_id)
        if binding is None:
            raise HTTPException(
                status_code=422,
                detail="Every plan step must have one explicit tool binding",
            )
        if len(step.required_capabilities) != 1:
            raise HTTPException(
                status_code=409,
                detail="V1 requires exactly one declared capability per plan step",
            )
        if binding.tool_name != step.required_capabilities[0]:
            raise HTTPException(
                status_code=422,
                detail="Tool name must exactly match the step's declared capability",
            )
        ordered_bindings.append(binding)

    if set(by_step_id) != {step.step_id for step in ordered_steps}:
        raise HTTPException(status_code=422, detail="Unexpected plan step bindings were supplied")

    risk_material = work_order.model_dump(mode="json")
    risk_material["verification_steps"] = [
        *risk_material.get("verification_steps", []),
        *[
            f"{step.description} {step.verification}"
            for step in execution_plan.steps
        ],
    ]
    derived_risk = derive_server_risk_class(work_order.goal, risk_material)
    if derived_risk is not RiskClass.LOW or work_order.risk_class is not RiskClass.LOW:
        raise HTTPException(
            status_code=403,
            detail="V1 plan execution is restricted to server-classified low-risk goals",
        )

    permission_service = ToolPermissionService(tasks, AuditLogger(tasks))
    core = AgentCore(
        build_model_router(),
        registry,
        permission_provider=lambda: permission_service.active_permissions(owner_user_id),
    )
    tool_requests: list[AgentToolRequest] = []
    step_bindings: list[dict[str, str]] = []
    for binding in ordered_bindings:
        definition = definitions[binding.tool_name]
        normalized = definition.input_model.model_validate(binding.payload)
        tool_requests.append(
            AgentToolRequest(
                name=binding.tool_name,
                payload=normalized.model_dump(mode="json"),
            )
        )
        step_bindings.append(
            {
                "step_id": binding.step_id,
                "tool_name": binding.tool_name,
                "tool_contract_digest": contract_digests[binding.tool_name],
            }
        )

    agent_request = AgentPlanRequest(
        goal=work_order.goal,
        requires_text=True,
        requires_tool_calling=False,
        tools=tool_requests,
    )
    try:
        agent_plan = core.plan(agent_request)
    except (LookupError, ValueError) as exc:
        raise HTTPException(status_code=503, detail="Agent execution planning is unavailable") from exc
    if not agent_plan.get("execution_ready"):
        raise HTTPException(
            status_code=403,
            detail="Current owner permissions or server policy do not allow this workflow",
        )

    audit_logger = AuditLogger(tasks)
    try:
        audit_logger.record(
            event_type="agent.plan_execution_preflight",
            outcome="allow",
            actor_type="user",
            actor_id=owner_user_id,
            subject_type="work_order_plan",
            subject_id=str(plan_id),
            metadata={
                "status": "preflight_passed",
                "risk_class": RiskClass.LOW.value,
                "decision": "allow",
                "tool_calls": len(ordered_bindings),
                "required_capability_count": len(ordered_bindings),
            },
        )
    except sqlite3.Error as exc:
        raise HTTPException(
            status_code=503,
            detail="Audit storage is unavailable; plan execution was not queued",
        ) from exc

    execution_payload = {
        "format": PLAN_EXECUTION_FORMAT,
        "request": agent_request.model_dump(mode="json"),
        "plan_binding": {
            "plan_id": record.plan_id,
            "plan_digest": record.plan_digest,
            "step_bindings": step_bindings,
        },
    }
    task = TaskRecord(
        task_type="agent.workflow",
        description="GPI/AWI plan execution",
        risk_class=RiskClass.LOW,
    )
    workflow_id = uuid4()
    try:
        workflow_envelope = encrypt_payload(
            execution_payload,
            workflow_id=str(workflow_id),
            task_id=str(task.task_id),
            owner_user_id=owner_user_id,
            key=load_payload_key(),
        )
    except PayloadEnvelopeError as exc:
        raise HTTPException(
            status_code=503,
            detail="The workflow payload could not be encrypted safely",
        ) from exc

    workflow_steps: list[dict[str, object]] = [
        {
            "step_number": 1,
            "kind": "provider_selection",
            "name": "provider_selection",
        }
    ]
    for index, binding in enumerate(ordered_bindings, start=2):
        definition = definitions[binding.tool_name]
        workflow_steps.append(
            {
                "step_number": index,
                "kind": "external_tool" if definition.external_side_effect else "safe_tool",
                "name": binding.tool_name,
            }
        )

    try:
        recovery.create_run(
            request_digest,
            workflow_steps,
            task=task,
            owner_user_id=owner_user_id,
            payload_envelope=workflow_envelope.model_dump(mode="json"),
            workflow_id=workflow_id,
            idempotency_binding={
                "scope": idempotency_scope,
                "key": idempotency_key,
            },
            plan_consumption={
                "plan_id": record.plan_id,
                "owner_user_id": owner_user_id,
                "plan_digest": record.plan_digest,
            },
        )
    except WorkflowRecoveryError as exc:
        raise HTTPException(status_code=409, detail="Plan could not be consumed atomically") from exc
    except sqlite3.IntegrityError:
        # A concurrent identical request may have won the idempotency race.
        existing = idempotency.get(idempotency_scope, idempotency_key)
        if existing is None or not hmac.compare_digest(
            existing.request_digest,
            request_digest,
        ) or not existing.workflow_id:
            raise HTTPException(status_code=409, detail="Plan or idempotency binding changed")
        stored_workflow = recovery.get_run(
            UUID(existing.workflow_id),
            owner_user_id=owner_user_id,
        )
        if stored_workflow is None:
            raise HTTPException(status_code=409, detail="The original workflow is unavailable")
        return {
            "workflow": stored_workflow,
            "execution": None,
            "queued": True,
            "idempotent_replay": True,
            "plan_consumed": True,
            "execution_started": False,
            "tools_executed": False,
            "permissions_changed": False,
        }
    except sqlite3.Error as exc:
        raise HTTPException(status_code=503, detail="Workflow storage is unavailable") from exc

    audit_recorded = True
    try:
        audit_logger.record(
            event_type="agent.plan_execution_queued",
            outcome="queued",
            actor_type="user",
            actor_id=owner_user_id,
            subject_type="workflow",
            subject_id=str(workflow_id),
            metadata={
                "status": "queued",
                "risk_class": RiskClass.LOW.value,
                "decision": "allow",
                "tool_calls": len(ordered_bindings),
                "required_capability_count": len(ordered_bindings),
            },
        )
    except sqlite3.Error:
        # The preflight audit is durable. Never turn a committed queue operation
        # into an apparent API failure just because its follow-up event failed.
        audit_recorded = False
    stored_workflow = recovery.get_run(workflow_id, owner_user_id=owner_user_id)
    return {
        "workflow": stored_workflow,
        "execution": None,
        "queued": True,
        "idempotent_replay": False,
        "plan_consumed": True,
        "execution_started": False,
        "tools_executed": False,
        "permissions_changed": False,
        "audit_recorded": audit_recorded,
    }


@router.post("/work-orders/assess")
def assess_agent_work_order(
    request: WorkOrder,
    current_user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> dict[str, object]:
    """Assess declared capability coverage without authorizing or executing tools."""
    settings = get_settings()
    tasks = TaskRepository(settings.database_path)
    tasks.initialize()
    registry = build_tool_registry(owner_user_id=current_user.user_id)
    try:
        assessment = assess_work_order_capabilities(request, registry.catalog())
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=503,
            detail="Registered tool catalog is not valid for capability assessment",
        ) from exc

    assessment_id = str(uuid4())
    AuditLogger(tasks).record(
        event_type="agent.work_order_assessed",
        outcome="complete" if assessment.complete else "capability_gaps",
        subject_type="work_order_assessment",
        subject_id=assessment_id,
        actor_type="user",
        actor_id=current_user.user_id,
        metadata={
            "required_capability_count": len(assessment.required),
            "available_capability_count": len(assessment.available),
            "missing_capability_count": len(assessment.missing),
            "declared_risk_class": request.risk_class.value,
            "declared_risk_is_authoritative": False,
        },
    )
    return {
        "assessment_id": assessment_id,
        "work_order": request.model_dump(mode="json"),
        "capabilities": assessment.as_dict(),
        "readiness": (
            "capabilities_present" if assessment.complete else "capability_gaps"
        ),
        "execution_started": False,
        "tools_executed": False,
        "authorization_checked": False,
        "declared_risk_is_authoritative": False,
    }


@router.get("/capabilities")
def discover_agent_capabilities() -> dict[str, object]:
    """Return a read-only inventory of configured models, tools, and reviewed sources."""
    settings = get_settings()
    models = build_model_router().catalog()
    tool_registry = build_tool_registry()
    tools = tool_registry.catalog()
    agents = build_default_agent_registry(tool_registry).catalog()
    approved_sources = CapabilityRegistry(settings.database_path).list_candidates(
        status="approved", limit=100
    )
    return {
        "schema_version": "1.0",
        "integration_contract_version": INTEGRATION_CONTRACT_VERSION,
        "discovery_mode": "read_only",
        "models": [
            {
                "provider": item.provider,
                "model": item.model,
                "local": item.local,
                "priority": item.priority,
                "capabilities": {
                    "text": item.capability.text,
                    "vision": item.capability.vision,
                    "audio": item.capability.audio,
                    "tool_calling": item.capability.tool_calling,
                },
            }
            for item in models
        ],
        "tools": tools,
        "agents": agents,
        "capability_sources": [
            {
                "candidate_id": item.candidate_id,
                "display_name": item.display_name,
                "integration_type": item.integration_type,
                "capabilities": list(item.capabilities),
                "license_id": item.license_id,
                "status": item.status,
            }
            for item in approved_sources
        ],
        "integrations": {
            "assistant_gateway": {
                "enabled": settings.assistant_gateway_enabled,
                "configured": bool(settings.assistant_gateway_base_url),
                "health_status": "not_checked",
                "status_endpoint": "/integrations/assistant-gateway/status",
            },
            "code_engine": {
                "enabled": settings.code_engine_enabled,
                "configured": bool(settings.code_engine_base_url),
                "health_status": "not_checked",
                "status_endpoint": "/integrations/code-engine/status",
            },
        },
        "execution_started": False,
        "network_probes_performed": False,
        "downloads_started": False,
    }


@router.post("/plan")
def create_agent_plan(
    request: AgentPlanRequest,
    current_user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> dict[str, object]:
    core = _build_owner_agent_core(current_user.user_id)
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
    core = _build_owner_agent_core(current_user.user_id)
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


@router.get("/workflows")
def list_agent_workflows(
    current_user: Annotated[AuthenticatedUser, Depends(require_user)],
    limit: int = Query(default=50, ge=1, le=100),
) -> dict[str, object]:
    """List only the authenticated owner's bounded workflow metadata."""
    settings = get_settings()
    tasks = TaskRepository(settings.database_path)
    tasks.initialize()
    workflows = WorkflowRecoveryRepository(settings.database_path).list_runs(
        owner_user_id=current_user.user_id,
        limit=limit,
    )
    return {"workflows": workflows, "count": len(workflows)}


@router.post("/workflows")
def execute_agent_workflow(
    request: AgentPlanRequest,
    current_user: Annotated[AuthenticatedUser, Depends(require_user)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key", min_length=1, max_length=255)] = None,
) -> dict[str, object]:
    """Validate and durably enqueue a workflow; execution belongs to WorkerEngine."""
    settings = get_settings()
    tasks = TaskRepository(settings.database_path)
    tasks.initialize()
    core = _build_owner_agent_core(current_user.user_id, tasks)
    try:
        plan = core.plan(request)
        request_digest = _workflow_digest(request)
        if not plan.get("execution_ready"):
            legacy = AgentWorkflowRepository(settings.database_path)
            workflow = legacy.create(request_digest, plan, owner_user_id=current_user.user_id)
            return {"workflow": workflow, "execution": None}

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
    except WorkflowRecoveryError as exc:
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
    core = _build_owner_agent_core(current_user.user_id, tasks)
    try:
        plan = core.plan(request.request)
        return AgentWorkflowRunner(tasks, core).queue_resume(
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
