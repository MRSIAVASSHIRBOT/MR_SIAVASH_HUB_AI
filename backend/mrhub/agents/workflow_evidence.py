"""Trusted, owner-scoped verification of durable Hub workflow-step evidence."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from mrhub.agents.plan_repository import AgentWorkOrderPlanRepository
from mrhub.agents.work_order_evidence import (
    EvidenceReference,
    EvidenceVerification,
    EvidenceVerifierRegistry,
    VerifierStatus,
    WorkOrderCriterion,
)
from mrhub.jobs.recovery import WorkflowRecoveryRepository

_CRITERION_PATTERN = re.compile(r"^workflow_step_succeeded:([a-z][a-z0-9_-]{0,39})$")
_SOURCE_PATTERN = re.compile(r"^([0-9a-f-]{36})/([a-z][a-z0-9_-]{0,39})$")


def _canonical_digest(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def verify_workflow_step_evidence(
    reference: EvidenceReference,
    criterion: WorkOrderCriterion,
    *,
    repository: WorkflowRecoveryRepository,
    plan_repository: AgentWorkOrderPlanRepository,
) -> EvidenceVerification:
    """Verify one exact owner-owned workflow step within the persisted AWI plan scope."""
    criterion_match = _CRITERION_PATTERN.fullmatch(criterion.description)
    source_match = _SOURCE_PATTERN.fullmatch(reference.source_ref)
    if criterion_match is None or source_match is None:
        return EvidenceVerification(
            VerifierStatus.UNKNOWN,
            reason_code="unsupported_criterion_verification",
        )

    expected_step_key = criterion_match.group(1)
    workflow_text, source_step_key = source_match.groups()
    bindings = dict(criterion.step_capability_bindings)
    expected_capabilities = bindings.get(expected_step_key)
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
    if not expected_capabilities:
        return EvidenceVerification(
            VerifierStatus.UNKNOWN,
            reason_code="criterion_capability_scope_missing",
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
    if not reference.owner_user_id:
        return EvidenceVerification(
            VerifierStatus.UNKNOWN,
            reason_code="evidence_owner_context_missing",
        )
    if not isinstance(reference.plan_id, str) or not reference.plan_id:
        return EvidenceVerification(
            VerifierStatus.UNKNOWN,
            reason_code="work_order_plan_binding_missing",
        )
    try:
        plan_record = plan_repository.get(
            reference.plan_id,
            owner_user_id=reference.owner_user_id,
        )
    except Exception:  # noqa: BLE001 - unavailable binding evidence remains unknown.
        return EvidenceVerification(
            VerifierStatus.UNKNOWN,
            reason_code="work_order_plan_lookup_unavailable",
        )
    if (
        plan_record is None
        or plan_record.status != "consumed"
        or plan_record.workflow_id != workflow_text
    ):
        return EvidenceVerification(
            VerifierStatus.UNKNOWN,
            reason_code="workflow_not_bound_to_work_order_plan",
        )
    if plan_record.expires_at <= datetime.now(UTC).isoformat():
        return EvidenceVerification(
            VerifierStatus.UNKNOWN,
            reason_code="work_order_plan_expired",
        )

    try:
        workflow = repository.get_run(
            workflow_id,
            owner_user_id=reference.owner_user_id,
        )
    except Exception:  # noqa: BLE001 - unavailable evidence remains unknown.
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
            "step_name": step_name,
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


def build_default_work_order_evidence_verifiers(
    database_path: Path,
) -> EvidenceVerifierRegistry:
    """Build the fixed server-owned verifier allow-list for this Hub process."""
    repository = WorkflowRecoveryRepository(database_path)
    plan_repository = AgentWorkOrderPlanRepository(database_path)
    registry = EvidenceVerifierRegistry()
    registry.register(
        source_type="agent_workflow_step",
        verifier_id="hub.workflow_step.v1",
        verifier=lambda reference, criterion: verify_workflow_step_evidence(
            reference,
            criterion,
            repository=repository,
            plan_repository=plan_repository,
        ),
    )
    return registry
