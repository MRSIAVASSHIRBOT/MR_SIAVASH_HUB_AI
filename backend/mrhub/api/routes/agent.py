"""Authenticated agent planning API."""

import hashlib
import hmac
import json
import sqlite3
from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from mrhub.agents.awi_planner import ExecutionPlan, PlanningError, generate_execution_plan
from mrhub.agents.core import AgentCore, AgentPlanRequest
from mrhub.agents.goal_analysis import analyze_goal
from mrhub.agents.gpi import (
    WorkOrderGenerationError,
    derive_server_risk_class,
    generate_work_order,
)
from mrhub.agents.lessons import LessonEvidence, LessonProposalError, build_lesson_proposal
from mrhub.agents.plan_repository import (
    AgentWorkOrderPlanError,
    AgentWorkOrderPlanRepository,
)
from mrhub.agents.registry import build_default_agent_registry
from mrhub.agents.repository import AgentRunRepository
from mrhub.agents.work_order import WorkOrder, assess_work_order_capabilities
from mrhub.agents.work_order_evidence import (
    EvidenceInputError,
    EvidenceReference,
    EvidenceVerifierRegistry,
    WorkOrderCriterion,
    WorkOrderSnapshot,
    evaluate_work_order_evidence,
)
from mrhub.agents.work_order_intelligence import assess_work_order_intelligence
from mrhub.agents.workflow_repository import AgentWorkflowRepository
from mrhub.agents.workflow_runner import AgentWorkflowRunner
from mrhub.api.dependencies import require_user
from mrhub.api.routes.models import build_model_router
from mrhub.capabilities.registry import CapabilityRegistry
from mrhub.config import get_settings
from mrhub.domain.tasks import RiskClass, TaskRecord
from mrhub.infrastructure.database import TaskRepository
from mrhub.integrations.health_probe import INTEGRATION_CONTRACT_VERSION
from mrhub.jobs.idempotency import IdempotencyError, IdempotencyRepository
from mrhub.jobs.payload_envelope import (
    PayloadEnvelopeError,
    decrypt_plan_payload,
    encrypt_payload,
    encrypt_plan_payload,
    load_payload_key,
)
from mrhub.jobs.recovery import WorkflowRecoveryError, WorkflowRecoveryRepository
from mrhub.providers.base import ProviderError
from mrhub.prompts.registry import DEFAULT_PROMPT_REGISTRY
from mrhub.providers.router import ModelRequest
from mrhub.security.audit import AuditLogger
from mrhub.security.auth import AuthenticatedUser
from mrhub.security.tool_approvals import (
    ToolApprovalError,
    ToolInvocationApprovalStore,
    canonical_tool_payload,
    tool_definition_fingerprint,
)
from mrhub.security.tool_permissions import ToolPermissionService
from mrhub.tools.builtins import build_tool_registry

router = APIRouter(prefix="/agent", tags=["agent"], dependencies=[Depends(require_user)])


def _build_owner_agent_core(
    owner_user_id: str,
    repository: TaskRepository | None = None,
    *,
    resume_workflow_id: UUID | None = None,
    resume_request: AgentPlanRequest | None = None,
) -> AgentCore:
    """Build an owner-scoped AgentCore with action-bound approval receipts."""
    tasks = repository or TaskRepository(get_settings().database_path)
    tasks.initialize()
    audit = AuditLogger(tasks)
    permissions = ToolPermissionService(tasks, audit)
    registry = build_tool_registry(owner_user_id=owner_user_id)
    approval_store = ToolInvocationApprovalStore(tasks)

    def resolve_approval(
        approval_id: str,
        tool_name: str,
        payload: dict[str, object],
        granted_permissions: frozenset[str],
        *,
        consume: bool,
    ) -> bool:
        """Validate or consume only a receipt for this exact currently-authorized action."""
        try:
            tool = registry.get(tool_name)
            # The caller reaches this helper only when policy evaluation identified
            # an approval-required tool. Rechecking required grants here prevents
            # consuming a receipt after a concurrent permission revocation.
            if not (tool.risk_class.value == "high" or tool.external_side_effect):
                return False
            if not tool.required_permissions.issubset(granted_permissions):
                return False
            _normalized, payload_digest = canonical_tool_payload(tool, payload)
            fingerprint = tool_definition_fingerprint(tool)
            if consume:
                audit_event = audit.build_event(
                    event_type="tool.approval_consumed",
                    outcome="consumed",
                    subject_id=approval_id,
                    subject_type="tool_approval",
                    actor_type="user",
                    actor_id=owner_user_id,
                    metadata={
                        "tool_name": tool_name,
                        "approval_id": approval_id,
                        "status": "consumed",
                        "decision": "consumed",
                        "reason_code": "single_use_receipt_consumed",
                    },
                ).model_dump(mode="json")
                return approval_store.consume(
                    approval_id,
                    owner_user_id=owner_user_id,
                    tool_name=tool_name,
                    payload_digest=payload_digest,
                    tool_fingerprint=fingerprint,
                    audit_event=audit_event,
                )
            if approval_store.validate(
                approval_id,
                owner_user_id=owner_user_id,
                tool_name=tool_name,
                payload_digest=payload_digest,
                tool_fingerprint=fingerprint,
            ):
                return True
            if resume_workflow_id is not None and resume_request is not None:
                return AgentWorkflowRunner.completed_approval_checkpoint_matches(
                    WorkflowRecoveryRepository(tasks.database_path),
                    resume_workflow_id,
                    owner_user_id,
                    resume_request,
                    approval_id,
                    tool_name,
                    payload,
                )
            return False
        except (LookupError, ToolApprovalError, TypeError, ValueError):
            return False
        except Exception:  # noqa: BLE001 - receipt checks fail closed
            return False

    return AgentCore(
        build_model_router(),
        registry,
        permission_provider=lambda: permissions.active_permissions(owner_user_id),
        approval_validator=lambda approval_id, tool_name, payload, grants: resolve_approval(
            approval_id, tool_name, payload, grants, consume=False
        ),
        approval_consumer=lambda approval_id, tool_name, payload, grants: resolve_approval(
            approval_id, tool_name, payload, grants, consume=True
        ),
    )

class WorkflowReconciliationRequest(BaseModel):
    step_number: int | None = Field(default=None, ge=1)
    step_id: str | None = Field(default=None, min_length=1, max_length=64, pattern="^[a-z][a-z0-9-]{0,63}$")
    outcome: Literal["succeeded", "failed"]
    output_digest: str | None = Field(default=None, pattern="^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def require_exactly_one_step_identity(self) -> "WorkflowReconciliationRequest":
        if (self.step_number is None) == (self.step_id is None):
            raise ValueError("Provide exactly one of step_id or step_number")
        return self

    def resolved_step_identity(self) -> int | str:
        if self.step_id is not None:
            return self.step_id
        if self.step_number is not None:
            return self.step_number
        raise ValueError("Workflow reconciliation step identity is missing")


class WorkflowResumeCheckRequest(BaseModel):
    request: AgentPlanRequest


class WorkflowLessonPreviewRequest(BaseModel):
    """A user-authored lesson candidate linked to one persisted successful step."""

    model_config = ConfigDict(extra="forbid")

    step_id: str = Field(
        min_length=1,
        max_length=64,
        pattern="^[a-z][a-z0-9-]{0,63}$",
        strict=True,
    )
    category: str = Field(min_length=1, max_length=80, pattern=r"^[\w .:/-]+$", strict=True)
    lesson_text: str = Field(min_length=20, max_length=500, strict=True)

    @field_validator("category", "lesson_text")
    @classmethod
    def normalize_lesson_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Lesson fields must not be blank")
        return normalized


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


class EvidenceReferenceInput(BaseModel):
    """Opaque evidence reference; callers cannot submit verifier status or payload."""

    model_config = ConfigDict(extra="forbid")

    evidence_id: str = Field(min_length=1, max_length=80, pattern=r"^[a-z][a-z0-9._:-]{0,79}$")
    criterion_id: str = Field(min_length=6, max_length=6, pattern=r"^ac_[0-9]{3}$")
    source_type: str = Field(min_length=1, max_length=80, pattern=r"^[a-z][a-z0-9._:-]{0,79}$")
    source_ref: str = Field(min_length=1, max_length=160, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,159}$")
    evidence_digest: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    work_order_digest: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    work_order_revision: int = Field(ge=1, strict=True)
    observed_at: str = Field(min_length=1, max_length=40)
    verifier_id: str = Field(min_length=1, max_length=80, pattern=r"^[a-z][a-z0-9._:-]{0,79}$")


class WorkOrderEvidenceEvaluationRequest(BaseModel):
    """A bounded set of opaque references to review against one persisted plan."""

    model_config = ConfigDict(extra="forbid")

    evidence: list[EvidenceReferenceInput] = Field(default_factory=list, max_length=100)


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


_PERSISTED_PLAN_METADATA_FIELDS = (
    "decision_analysis",
    "planning_assessment",
    "model_selection",
    "prompt_templates",
)


def _extract_persisted_plan_metadata(payload: dict[str, object]) -> dict[str, object]:
    """Validate and retain optional, server-generated planner assessment metadata."""
    metadata: dict[str, object] = {}
    for field in _PERSISTED_PLAN_METADATA_FIELDS:
        if field not in payload:
            continue
        value = payload[field]
        if not isinstance(value, dict):
            raise PayloadEnvelopeError("Persisted plan assessment metadata is invalid")
        metadata[field] = value
    return metadata


@router.get("/prompts")
def list_prompt_templates() -> dict[str, object]:
    """Return exact prompt version metadata without exposing template source."""
    return DEFAULT_PROMPT_REGISTRY.catalog()


@router.post("/work-orders/analyze")
def analyze_goal_request(
    request: GoalPlanningRequest,
    current_user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> dict[str, object]:
    """Analyze goal complexity and routing signals without model or tool execution."""
    tasks = TaskRepository(get_settings().database_path)
    tasks.initialize()
    analysis = analyze_goal(request.goal)
    try:
        AuditLogger(tasks).record(
            event_type="agent.goal_analyzed",
            outcome="success",
            actor_type="user",
            actor_id=current_user.user_id,
            subject_type="goal",
            metadata={
                "status": "analyzed",
                "reason_code": "deterministic_goal_preflight",
            },
        )
    except sqlite3.Error as exc:
        raise HTTPException(
            status_code=503,
            detail="Audit storage is unavailable",
        ) from exc
    return {
        "analysis": analysis.model_dump(mode="json"),
        "planning_only": True,
        "execution_started": False,
        "tools_executed": False,
        "permissions_changed": False,
    }


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

    prompt_templates: dict[str, object] = {"renders": []}

    def record_prompt_render(rendered) -> None:
        renders = prompt_templates["renders"]
        if isinstance(renders, list):
            renders.append(rendered.metadata())

    try:
        # GPI/AWI planning is local-only in the zero-cost runtime profile.
        # Paid providers remain available only through their dedicated, explicit endpoints.
        model_router = build_model_router(
            provider_mode="local",
            include_stub=False,
            max_timeout_seconds=60,
        )
        selection = model_router.select(
            ModelRequest(requires_text=True, prefer_local=True)
        )
        work_order = generate_work_order(
            request.goal,
            model_router,
            prompt_observer=record_prompt_render,
        )
        decision_analysis = analyze_goal(request.goal, work_order=work_order)
        if work_order.risk_class.value == "prohibited":
            try:
                audit_logger.record(
                    event_type="agent.work_order_blocked",
                    outcome="denied",
                    actor_type="user",
                    actor_id=current_user.user_id,
                    subject_type="work_order",
                    metadata={"status": "generated_output_prohibited"},
                )
            except sqlite3.Error as audit_exc:
                raise HTTPException(
                    status_code=503,
                    detail="Audit storage is unavailable",
                ) from audit_exc
            raise HTTPException(
                status_code=422,
                detail="The requested goal is outside the supported safety policy",
            )
        plan = generate_execution_plan(
            work_order,
            model_router,
            prompt_observer=record_prompt_render,
        )
    except (WorkOrderGenerationError, PlanningError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(
            status_code=503,
            detail="No configured non-stub local model provider is available",
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

    try:
        planning_assessment = assess_work_order_intelligence(
            work_order, plan, assessment
        )
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=503,
            detail="Validated plan could not be assessed consistently",
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
        "decision_analysis": decision_analysis.model_dump(mode="json"),
        "plan": plan.model_dump(mode="json"),
        "planning_assessment": planning_assessment.as_dict(),
        "model_selection": {
            "provider": selection.provider,
            "model": selection.model,
            "local": selection.local,
            "rationale": selection.rationale,
        },
        "prompt_templates": prompt_templates,
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
    try:
        plan_metadata = _extract_persisted_plan_metadata(planned)
        payload = {
            "work_order": planned["work_order"],
            "plan": planned["plan"],
            **plan_metadata,
        }
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
        **plan_metadata,
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
        required_fields = {"work_order", "plan"}
        allowed_fields = required_fields | set(_PERSISTED_PLAN_METADATA_FIELDS)
        if not required_fields.issubset(payload) or not set(payload).issubset(allowed_fields):
            raise PayloadEnvelopeError("Agent plan payload shape is invalid")
        plan_metadata = _extract_persisted_plan_metadata(payload)
        work_order = WorkOrder.model_validate(payload["work_order"])
        plan = ExecutionPlan.model_validate(payload["plan"])
        canonical = {
            "work_order": work_order.model_dump(mode="json"),
            "plan": plan.model_dump(mode="json"),
            **plan_metadata,
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

    try:
        decision_analysis = analyze_goal(work_order.goal, work_order=work_order)
        planning_assessment = assess_work_order_intelligence(
            work_order, plan, assessment
        )
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=409,
            detail="Persisted plan assessment could not be recomputed safely",
        ) from exc

    return {
        "plan_id": record.plan_id,
        "status": record.status,
        "plan_digest": record.plan_digest,
        "created_at": record.created_at,
        "expires_at": record.expires_at,
        "work_order": work_order.model_dump(mode="json"),
        "plan": plan.model_dump(mode="json"),
        **{
            key: value
            for key, value in plan_metadata.items()
            if key in {"model_selection", "prompt_templates"}
        },
        "decision_analysis": decision_analysis.model_dump(mode="json"),
        "planning_assessment": planning_assessment.as_dict(),
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




@router.post("/work-orders/plans/{plan_id}/evidence/evaluate")
def evaluate_persisted_work_order_evidence(
    plan_id: UUID,
    payload: WorkOrderEvidenceEvaluationRequest,
    current_user: Annotated[AuthenticatedUser, Depends(require_user)],
    response: Response,
    http_request: Request,
) -> dict[str, object]:
    """Evaluate opaque evidence for one active, owner-scoped encrypted plan.

    The plan digest is the immutable revision binding. Acceptance-criterion IDs
    are derived deterministically from the persisted WorkOrder order (ac_001...).
    Only verifiers registered in trusted server composition code can return a
    passed/failed outcome. An empty or unconfigured registry therefore fails
    closed as review_required.
    """
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["Pragma"] = "no-cache"
    response.headers["X-Content-Type-Options"] = "nosniff"

    settings = get_settings()
    tasks = TaskRepository(settings.database_path)
    tasks.initialize()
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
        stored_payload = decrypt_plan_payload(
            record.envelope,
            plan_id=record.plan_id,
            owner_user_id=record.owner_user_id,
            key=key,
        )
        required_fields = {"work_order", "plan"}
        allowed_fields = required_fields | set(_PERSISTED_PLAN_METADATA_FIELDS)
        if (
            not required_fields.issubset(stored_payload)
            or not set(stored_payload).issubset(allowed_fields)
        ):
            raise PayloadEnvelopeError("Agent plan payload shape is invalid")
        plan_metadata = _extract_persisted_plan_metadata(stored_payload)
        work_order = WorkOrder.model_validate(stored_payload["work_order"])
        plan = ExecutionPlan.model_validate(stored_payload["plan"])
        canonical = {
            "work_order": work_order.model_dump(mode="json"),
            "plan": plan.model_dump(mode="json"),
            **plan_metadata,
        }
        digest = _canonical_plan_digest(canonical)
        if not hmac.compare_digest(digest, record.plan_digest):
            raise PayloadEnvelopeError("Agent plan digest does not match its stored record")
    except (PayloadEnvelopeError, ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=409,
            detail="Plan record failed integrity or schema validation",
        ) from exc

    criteria = tuple(
        WorkOrderCriterion(criterion_id=f"ac_{index:03d}", required=True)
        for index, _criterion in enumerate(work_order.acceptance_criteria, start=1)
    )
    work_order_digest = _canonical_plan_digest(
        {"work_order": work_order.model_dump(mode="json")}
    )
    snapshot = WorkOrderSnapshot(
        work_order_id=f"plan-{record.plan_id}",
        revision=1,
        digest=work_order_digest,
        criteria=criteria,
    )
    references = tuple(
        EvidenceReference(**item.model_dump(mode="python"))
        for item in payload.evidence
    )
    verifiers = getattr(http_request.app.state, "work_order_evidence_verifiers", None)
    if not isinstance(verifiers, EvidenceVerifierRegistry):
        raise HTTPException(
            status_code=503,
            detail="Trusted WorkOrder evidence verifier registry is not initialized",
        )
    try:
        report = evaluate_work_order_evidence(snapshot, references, verifiers)
    except (EvidenceInputError, TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=422,
            detail="Evidence references do not match the versioned WorkOrder contract",
        ) from exc

    try:
        AuditLogger(tasks).record(
            event_type="agent.work_order_evidence_evaluated",
            outcome=report.decision.value,
            actor_type="user",
            actor_id=current_user.user_id,
            subject_type="agent_work_order_plan",
            subject_id=record.plan_id,
            metadata={
                "status": "read_only_evaluation",
                "decision": report.decision.value,
                "evidence_count": len(references),
                "criterion_count": len(criteria),
                "report_digest": report.report_digest,
            },
        )
    except sqlite3.Error as exc:
        raise HTTPException(
            status_code=503,
            detail="Audit storage is unavailable",
        ) from exc

    return {
        "plan_id": record.plan_id,
        "plan_digest": record.plan_digest,
        "work_order_digest": work_order_digest,
        "work_order_revision": 1,
        "plan_revision": 1,
        "criteria_map": {
            f"ac_{index:03d}": criterion
            for index, criterion in enumerate(work_order.acceptance_criteria, start=1)
        },
        "report": report.as_dict(),
        "read_only": True,
        "execution_started": False,
        "tools_executed": False,
        "permissions_changed": False,
    }


@router.delete("/work-orders/plans/{plan_id}")
def revoke_persisted_goal_work_order_plan(
    plan_id: UUID,
    current_user: Annotated[AuthenticatedUser, Depends(require_user)],
    response: Response,
) -> dict[str, object]:
    """Revoke an owned active plan and erase its ciphertext without executing it."""
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["Pragma"] = "no-cache"
    response.headers["X-Content-Type-Options"] = "nosniff"
    settings = get_settings()
    tasks = TaskRepository(settings.database_path)
    tasks.initialize()
    try:
        AuditLogger(tasks).record(
            event_type="agent.work_order_plan_revocation_requested",
            outcome="requested",
            actor_type="user",
            actor_id=current_user.user_id,
            subject_type="agent_work_order_plan",
            subject_id=str(plan_id),
            metadata={"status": "revocation_requested", "decision": "revoke"},
        )
    except sqlite3.Error as exc:
        raise HTTPException(
            status_code=503,
            detail="Audit storage is unavailable",
        ) from exc

    record = AgentWorkOrderPlanRepository(settings.database_path).revoke(
        str(plan_id),
        owner_user_id=current_user.user_id,
    )
    if record is None:
        raise HTTPException(status_code=404, detail="Plan record not found")
    if record.status == "expired":
        raise HTTPException(status_code=410, detail="Plan record has expired")
    if record.status == "consumed":
        raise HTTPException(status_code=409, detail="Consumed plan cannot be revoked")
    if record.status != "revoked":
        raise HTTPException(status_code=409, detail="Plan record is not revocable")
    return {
        "plan_id": record.plan_id,
        "status": "revoked",
        "revoked": True,
        "ciphertext_erased": True,
        "execution_started": False,
        "tools_executed": False,
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
def discover_agent_capabilities(
    current_user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> dict[str, object]:
    """Return the authenticated owner's read-only inventory of configured tools and sources."""
    settings = get_settings()
    models = build_model_router().catalog()
    tool_registry = build_tool_registry(owner_user_id=current_user.user_id)
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
    """Use the version-stable request digest shared with worker replay."""
    return AgentWorkflowRunner.request_digest(request)


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


@router.get("/traces/{trace_id}")
def get_agent_trace(
    trace_id: UUID,
    current_user: Annotated[AuthenticatedUser, Depends(require_user)],
    limit: int = Query(default=20, ge=1, le=50),
    before_created_at: str | None = Query(default=None, max_length=40),
    before_event_id: UUID | None = None,
) -> dict[str, object]:
    """Return one bounded, owner-scoped task/workflow execution timeline.

    The trace ID is the server-generated task UUID, not a credential or a
    client-controlled correlation token. HTTP request IDs remain separate.
    """
    if (before_created_at is None) != (before_event_id is None):
        raise HTTPException(
            status_code=422,
            detail="Both cursor fields must be provided together",
        )
    before = None
    if before_created_at is not None and before_event_id is not None:
        try:
            parsed_cursor_time = datetime.fromisoformat(before_created_at)
            if parsed_cursor_time.tzinfo is None or parsed_cursor_time.utcoffset() is None:
                raise ValueError("timezone offset is required")
            # Database timestamps are stored in UTC ISO-8601 form. Canonicalize
            # equivalent offsets before applying the lexicographic keyset cursor.
            canonical_cursor_time = parsed_cursor_time.astimezone(UTC).isoformat()
        except (OverflowError, ValueError) as exc:
            raise HTTPException(
                status_code=422,
                detail="Invalid timezone-aware trace cursor timestamp",
            ) from exc
        before = (canonical_cursor_time, str(before_event_id))

    settings = get_settings()
    tasks = TaskRepository(settings.database_path)
    tasks.initialize()
    owned_trace = tasks.get_owned_task_trace(trace_id, current_user.user_id)
    if owned_trace is None:
        raise HTTPException(status_code=404, detail="Execution trace not found")

    page = tasks.list_task_audit_event_page(trace_id, limit=limit, before=before)
    events = page["events"]
    next_cursor = None
    if page["has_more"] and events:
        last_event = events[-1]
        next_cursor = {
            "before_created_at": last_event["created_at"],
            "before_event_id": last_event["event_id"],
        }
    return {
        "trace_id": str(trace_id),
        "task_id": owned_trace["task_id"],
        "workflow_id": owned_trace["workflow_id"],
        "events": events,
        "has_more": page["has_more"],
        "next_cursor": next_cursor,
        "limitations": [
            "The current trace scope is one task and its task-linked workflow.",
            "Trace events contain allow-listed metadata, not raw prompts or tool payloads.",
            "Request IDs identify HTTP requests and are distinct from execution trace IDs.",
        ],
    }


@router.post("/workflows")
def execute_agent_workflow(
    request: AgentPlanRequest,
    current_user: Annotated[AuthenticatedUser, Depends(require_user)],
    response: Response,
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
                request.canonical_payload(),
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
                        replay_task_id = existing.get("task_id")
                        if isinstance(replay_task_id, str):
                            response.headers["X-Trace-ID"] = replay_task_id
                        return {
                            "workflow": existing,
                            "execution": None,
                            "idempotent_replay": True,
                            "trace_id": replay_task_id,
                        }
                raise HTTPException(
                    status_code=409,
                    detail="Request is already being created or requires recovery",
                )
            idempotency_binding = {"scope": scope, "key": idempotency_key}

        raw_steps = plan.get("steps", [])
        if not isinstance(raw_steps, list) or not raw_steps:
            raise HTTPException(status_code=422, detail="Workflow plan contains no executable steps")
        step_specs, _tools_by_execution_step = (
            AgentWorkflowRunner.build_durable_step_metadata(core, request, plan)
        )

        try:
            recovery.create_run(
                request_digest,
                step_specs,
                task=task,
                definition_version=3,
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
                        replay_task_id = existing.get("task_id")
                        if isinstance(replay_task_id, str):
                            response.headers["X-Trace-ID"] = replay_task_id
                        return {
                            "workflow": existing,
                            "execution": None,
                            "idempotent_replay": True,
                            "trace_id": replay_task_id,
                        }
            raise HTTPException(
                status_code=409,
                detail="Workflow submission conflicts with an existing resource",
            ) from exc
        trace_id = str(task.task_id)
        response.headers["X-Trace-ID"] = trace_id
        AuditLogger(tasks).record(
            event_type="task.submitted",
            outcome="queued",
            subject_id=str(task.task_id),
            actor_type="user",
            actor_id=current_user.user_id,
            metadata={
                "task_type": task.task_type,
                "risk_class": task.risk_class.value,
                "decision": "allow",
                "trace_id": trace_id,
                "workflow_id": str(workflow_id),
            },
        )
        return {
            "workflow": recovery.get_run(workflow_id, owner_user_id=current_user.user_id),
            "execution": None,
            "queued": True,
            "trace_id": trace_id,
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


@router.post("/workflows/{workflow_id}/lessons/preview")
def preview_workflow_lesson(
    workflow_id: UUID,
    payload: WorkflowLessonPreviewRequest,
    current_user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> dict[str, object]:
    """Preview a user-authored lesson linked to one persisted successful step.

    This endpoint never writes Memory. The owner must separately review and
    submit an explicit Memory create request if the proposal should be retained.
    """
    settings = get_settings()
    repository = WorkflowRecoveryRepository(settings.database_path)
    workflow = repository.get_run(
        workflow_id,
        owner_user_id=current_user.user_id,
    )
    if workflow is None:
        raise HTTPException(status_code=404, detail="Agent workflow not found")
    if workflow.get("status") != "succeeded":
        raise HTTPException(
            status_code=409,
            detail="Lessons require a successfully completed workflow",
        )

    steps = workflow.get("steps")
    if not isinstance(steps, list):
        raise HTTPException(status_code=409, detail="Workflow step evidence is unavailable")
    step = next(
        (
            item for item in steps
            if isinstance(item, dict) and item.get("step_key") == payload.step_id
        ),
        None,
    )
    if step is None:
        raise HTTPException(status_code=404, detail="Workflow step not found")

    try:
        proposal = build_lesson_proposal(
            LessonEvidence(
                workflow_id=workflow_id,
                workflow_status=str(workflow.get("status")),
                step_id=payload.step_id,
                step_status=str(step.get("status")),
                output_digest=step.get("output_digest")
                if isinstance(step.get("output_digest"), str)
                else None,
                error_code=step.get("error_code")
                if isinstance(step.get("error_code"), str)
                else None,
            ),
            category=payload.category,
            lesson_text=payload.lesson_text,
        )
    except LessonProposalError as exc:
        raise HTTPException(
            status_code=422,
            detail="Lesson proposal requires a completed evidence-backed workflow step and safe content",
        ) from exc

    tasks = TaskRepository(settings.database_path)
    tasks.initialize()
    try:
        AuditLogger(tasks).record(
            event_type="agent.lesson_previewed",
            outcome="owner_review_required",
            subject_type="lesson_proposal",
            subject_id=proposal.proposal_id,
            actor_type="user",
            actor_id=current_user.user_id,
            metadata={
                "status": "preview_only",
                "reason_code": "evidence_linked_lesson_preview",
                "proposal_count": 1,
                "state_changed": False,
            },
        )
    except sqlite3.Error as exc:
        raise HTTPException(
            status_code=503,
            detail="Lesson proposal audit storage is unavailable",
        ) from exc
    return {
        "workflow_id": str(workflow_id),
        "proposal": proposal.as_dict(),
    }


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
            request.resolved_step_identity(),
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
        workflow = recovery.get_run(
            workflow_id, owner_user_id=current_user.user_id
        )
        if workflow is None:
            raise HTTPException(status_code=404, detail="Workflow not found")
        decision = recovery.resume_decision(
            workflow_id,
            _workflow_digest(request.request),
            definition_version=int(workflow["definition_version"]),
            owner_user_id=current_user.user_id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="Workflow not found") from exc
    return {
        "workflow_id": str(workflow_id),
        "decision": decision.decision,
        "next_step": decision.next_step,
        "next_step_id": decision.next_step_id,
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
    core = _build_owner_agent_core(
        current_user.user_id,
        tasks,
        resume_workflow_id=workflow_id,
        resume_request=request.request,
    )
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
