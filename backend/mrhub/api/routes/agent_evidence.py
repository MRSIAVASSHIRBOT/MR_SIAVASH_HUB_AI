"""Owner-scoped, read-only WorkOrder evidence verification API."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import sqlite3
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator

from mrhub.agents.awi_planner import ExecutionPlan
from mrhub.agents.plan_repository import AgentWorkOrderPlanRepository
from mrhub.agents.work_order import WorkOrder
from mrhub.agents.work_order_correction import build_work_order_correction_proposal
from mrhub.agents.work_order_evidence import (
    EvidenceReference,
    EvidenceVerification,
    EvidenceVerifierRegistry,
    VerifierStatus,
    WorkOrderCriterion,
    WorkOrderSnapshot,
    evaluate_work_order_evidence,
)
from mrhub.api.dependencies import require_user
from mrhub.config import get_settings
from mrhub.infrastructure.database import TaskRepository
from mrhub.jobs.payload_envelope import (
    PayloadEnvelopeError,
    decrypt_plan_payload,
    load_payload_key,
)
from mrhub.jobs.recovery import WorkflowRecoveryRepository
from mrhub.security.audit import AuditLogger
from mrhub.security.auth import AuthenticatedUser

router = APIRouter(prefix="/agent", tags=["agent"], dependencies=[Depends(require_user)])

_METADATA_FIELDS = ("decision_analysis", "planning_assessment", "model_selection")
_CRITERION_PATTERN = re.compile(r"^workflow_step_succeeded:([a-z][a-z0-9-]{0,63})$")
_SOURCE_PATTERN = re.compile(r"^([0-9a-f-]{36})/([a-z][a-z0-9-]{0,63})$")


class WorkflowStepEvidenceInput(BaseModel):
    """Opaque reference to an owner-scoped Hub workflow step; never a status claim."""

    model_config = ConfigDict(extra="forbid", strict=True)

    evidence_id: str = Field(min_length=1, max_length=80, pattern=r"^[a-z][a-z0-9._:-]{0,79}$")
    criterion_id: str = Field(min_length=6, max_length=6, pattern=r"^ac_[0-9]{3}$")
    source_type: Literal["agent_workflow_step"]
    source_ref: str = Field(min_length=38, max_length=100, pattern=_SOURCE_PATTERN.pattern)
    evidence_digest: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    work_order_digest: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    work_order_revision: int = Field(ge=1, strict=True)
    observed_at: str = Field(min_length=1, max_length=40)
    verifier_id: Literal["hub.workflow_step.v1"]

    @field_validator("observed_at")
    @classmethod
    def require_timezone_aware_timestamp(cls, value: str) -> str:
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("Observed timestamp must be ISO-8601") from exc
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("Observed timestamp requires an explicit timezone")
        return value


class WorkOrderEvidenceEvaluationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    evidence: list[WorkflowStepEvidenceInput] = Field(default_factory=list, max_length=100)


def _canonical_digest(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _load_owned_plan(plan_id: UUID, owner_user_id: str, database_path):
    """Load one intact encrypted plan; return only the two validated contracts."""
    record = AgentWorkOrderPlanRepository(database_path).get(
        str(plan_id), owner_user_id=owner_user_id
    )
    if record is None:
        raise HTTPException(status_code=404, detail="Plan record not found")
    if record.status == "expired":
        raise HTTPException(status_code=410, detail="Plan record has expired")
    if record.status != "active":
        raise HTTPException(status_code=409, detail="Plan record is not available")

    try:
        key = load_payload_key()
        payload = decrypt_plan_payload(
            record.envelope,
            plan_id=record.plan_id,
            owner_user_id=record.owner_user_id,
            key=key,
        )
        required = {"work_order", "plan"}
        allowed = required | set(_METADATA_FIELDS)
        if not required.issubset(payload) or not set(payload).issubset(allowed):
            raise PayloadEnvelopeError("Persisted plan payload shape is invalid")
        metadata: dict[str, object] = {}
        for name in _METADATA_FIELDS:
            if name in payload:
                if not isinstance(payload[name], dict):
                    raise PayloadEnvelopeError("Persisted plan metadata is invalid")
                metadata[name] = payload[name]
        work_order = WorkOrder.model_validate(payload["work_order"])
        plan = ExecutionPlan.model_validate(payload["plan"])
        canonical = {
            "work_order": work_order.model_dump(mode="json"),
            "plan": plan.model_dump(mode="json"),
            **metadata,
        }
        if not hmac.compare_digest(_canonical_digest(canonical), record.plan_digest):
            raise PayloadEnvelopeError("Persisted plan digest mismatch")
    except PayloadEnvelopeError as exc:
        raise HTTPException(
            status_code=409,
            detail="Persisted plan failed integrity validation",
        ) from exc
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=409,
            detail="Persisted plan failed schema validation",
        ) from exc
    return record, work_order, plan


def _build_work_order_snapshot(plan_id: UUID, work_order: WorkOrder) -> WorkOrderSnapshot:
    """Bind generated acceptance criteria to one exact encrypted WorkOrder revision."""
    canonical_work_order = work_order.model_dump(mode="json")
    criteria = tuple(
        WorkOrderCriterion(
            criterion_id=f"ac_{index:03d}",
            required=True,
            description=description,
        )
        for index, description in enumerate(work_order.acceptance_criteria, start=1)
    )
    return WorkOrderSnapshot(
        work_order_id=f"wo_{plan_id.hex}",
        revision=1,
        digest=_canonical_digest(canonical_work_order),
        criteria=criteria,
    )


def _workflow_step_verifier(
    reference: EvidenceReference,
    criterion: WorkOrderCriterion,
    *,
    repository: WorkflowRecoveryRepository,
    owner_user_id: str,
    planned_step_capabilities: dict[str, frozenset[str]],
) -> EvidenceVerification:
    """Verify only the explicitly typed 'workflow step succeeded' criterion."""
    criterion_match = _CRITERION_PATTERN.fullmatch(criterion.description)
    source_match = _SOURCE_PATTERN.fullmatch(reference.source_ref)
    if criterion_match is None or source_match is None:
        return EvidenceVerification(
            VerifierStatus.UNKNOWN,
            reason_code="unsupported_criterion_verification",
        )

    expected_step_key = criterion_match.group(1)
    workflow_text, source_step_key = source_match.groups()
    expected_capabilities = planned_step_capabilities.get(expected_step_key)
    if expected_capabilities is None:
        return EvidenceVerification(
            VerifierStatus.UNKNOWN,
            reason_code="criterion_step_not_in_plan",
        )
    if source_step_key != expected_step_key:
        return EvidenceVerification(
            VerifierStatus.UNKNOWN,
            reason_code="criterion_source_mismatch",
        )
    try:
        workflow_id = UUID(workflow_text)
    except ValueError:
        return EvidenceVerification(
            VerifierStatus.UNKNOWN,
            reason_code="invalid_workflow_reference",
        )
    if str(workflow_id) != workflow_text:
        return EvidenceVerification(
            VerifierStatus.UNKNOWN,
            reason_code="invalid_workflow_reference",
        )

    try:
        workflow = repository.get_run(workflow_id, owner_user_id=owner_user_id)
    except Exception:  # noqa: BLE001 - an unavailable verifier cannot accept evidence.
        return EvidenceVerification(
            VerifierStatus.UNKNOWN,
            reason_code="workflow_lookup_unavailable",
        )
    if workflow is None:
        return EvidenceVerification(
            VerifierStatus.UNKNOWN,
            reason_code="workflow_not_found_or_not_owned",
        )

    steps = workflow.get("steps")
    if not isinstance(steps, list):
        return EvidenceVerification(
            VerifierStatus.UNKNOWN,
            reason_code="workflow_steps_unavailable",
        )
    step = next(
        (
            item for item in steps
            if isinstance(item, dict) and item.get("step_key") == source_step_key
        ),
        None,
    )
    if step is None:
        return EvidenceVerification(
            VerifierStatus.UNKNOWN,
            reason_code="workflow_step_not_found",
        )

    step_name = step.get("step_name")
    if not isinstance(step_name, str) or step_name not in expected_capabilities:
        return EvidenceVerification(
            VerifierStatus.UNKNOWN,
            reason_code="workflow_step_capability_mismatch",
        )

    status = step.get("status")
    if status == "succeeded":
        digest = step.get("output_digest")
        if not isinstance(digest, str):
            return EvidenceVerification(
                VerifierStatus.UNKNOWN,
                reason_code="workflow_step_digest_unavailable",
            )
        return EvidenceVerification(
            VerifierStatus.PASSED,
            evidence_digest=digest,
            reason_code="workflow_step_succeeded",
        )
    if status == "failed":
        failure_evidence = {
            "workflow_id": str(workflow_id),
            "step_id": source_step_key,
            "status": status,
            "error_code": step.get("error_code") or "tool_execution_failed",
            "attempt_count": step.get("attempt_count"),
            "started_at": step.get("started_at"),
            "finished_at": step.get("finished_at"),
        }
        return EvidenceVerification(
            VerifierStatus.FAILED,
            evidence_digest=_canonical_digest(failure_evidence),
            reason_code="workflow_step_failed",
        )
    return EvidenceVerification(
        VerifierStatus.UNKNOWN,
        reason_code="workflow_step_not_terminal",
    )


@router.post("/work-orders/plans/{plan_id}/evidence/evaluate")
def evaluate_plan_evidence(
    plan_id: UUID,
    request: WorkOrderEvidenceEvaluationRequest,
    current_user: Annotated[AuthenticatedUser, Depends(require_user)],
    response: Response,
) -> dict[str, object]:
    """Evaluate only server-verifiable evidence; never execute or authorize work."""
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["Pragma"] = "no-cache"
    response.headers["X-Content-Type-Options"] = "nosniff"
    settings = get_settings()
    tasks = TaskRepository(settings.database_path)
    tasks.initialize()
    record, work_order, plan = _load_owned_plan(
        plan_id, current_user.user_id, settings.database_path
    )
    declared_criteria = set(work_order.acceptance_criteria)
    planned_criteria = {
        criterion
        for step in plan.steps
        for criterion in step.verifies_criteria
    }
    if planned_criteria != declared_criteria:
        raise HTTPException(
            status_code=409,
            detail="Persisted plan does not cover the WorkOrder acceptance criteria",
        )
    planned_step_capabilities = {
        step.step_id: frozenset(step.required_capabilities)
        for step in plan.steps
    }
    snapshot = _build_work_order_snapshot(plan_id, work_order)

    references = tuple(
        EvidenceReference(**item.model_dump())
        for item in request.evidence
    )
    verifiers = EvidenceVerifierRegistry()
    workflow_repository = WorkflowRecoveryRepository(settings.database_path)
    verifiers.register(
        source_type="agent_workflow_step",
        verifier_id="hub.workflow_step.v1",
        verifier=lambda reference, criterion: _workflow_step_verifier(
            reference,
            criterion,
            repository=workflow_repository,
            owner_user_id=current_user.user_id,
            planned_step_capabilities=planned_step_capabilities,
        ),
    )
    try:
        report = evaluate_work_order_evidence(snapshot, references, verifiers)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="Evidence references are invalid") from exc

    decision = report.decision.value
    correction_proposal = build_work_order_correction_proposal(report)
    try:
        AuditLogger(tasks).record(
            event_type="agent.work_order_evidence_evaluated",
            outcome=decision,
            subject_type="agent_work_order_plan",
            subject_id=record.plan_id,
            actor_type="user",
            actor_id=current_user.user_id,
            metadata={
                "status": decision,
                "reason_code": "owner_scoped_workflow_evidence_v1",
                "proposal_count": len(references),
            },
        )
    except sqlite3.Error as exc:
        raise HTTPException(
            status_code=503,
            detail="Evidence audit storage is unavailable",
        ) from exc

    return {
        "plan_id": record.plan_id,
        "report": report.as_dict(),
        "correction_proposal": correction_proposal.as_dict(),
        "verifier_contract": "hub.workflow_step.v1",
        "decision_scope": "declared_work_order_acceptance_criteria_only",
        "goal_completion_claimed": False,
        "human_review_required_for_goal_completion": True,
        "verification_scope": (
            "Only an exact criterion formatted as "
            "'workflow_step_succeeded:<step_key>' can be independently checked "
            "by the current Hub workflow-step verifier. Other criterion types remain unknown."
        ),
        "read_only": True,
        "execution_started": False,
        "permissions_changed": False,
        "automatic_retry": False,
        "automatic_correction": False,
    }
