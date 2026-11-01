"""Worker-owned dispatch for durable, encrypted agent workflows."""
from __future__ import annotations

import hashlib
import json
import logging
from threading import Event
from uuid import UUID

from mrhub.agents.core import AgentCore, AgentPlanRequest
from mrhub.agents.execution_inputs import (
    ExecutionInputUnavailable,
    WorkflowExecutionInputRepository,
)
from mrhub.config import get_settings
from mrhub.domain.tasks import TaskRecord, TaskStatus
from mrhub.infrastructure.database import TaskRepository
from mrhub.jobs.leases import WorkerLease
from mrhub.jobs.recovery import StepAttempt, WorkflowRecoveryRepository

logger = logging.getLogger(__name__)


def workflow_digest(request: AgentPlanRequest) -> str:
    encoded = json.dumps(
        request.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def enqueue_workflow(
    repository: TaskRepository,
    core: AgentCore,
    request: AgentPlanRequest,
    plan: dict[str, object],
    request_digest: str,
    owner_user_id: str,
    submission_key: str | None = None,
) -> dict[str, object]:
    """Atomically create queued Job/Workflow; persist only encrypted bounded inputs."""
    settings = get_settings()
    inputs = WorkflowExecutionInputRepository(
        repository.database_path, settings.workflow_input_encryption_key
    )
    # Fail before creating durable work if encryption is unavailable or payload is invalid.
    inputs._cipher()
    payload = request.model_dump(mode="json")
    inputs._encode_payload(payload)

    raw_steps = plan.get("steps")
    if not isinstance(raw_steps, list) or not raw_steps:
        raise ValueError("Workflow plan contains no executable steps")
    step_specs: list[dict[str, object]] = []
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
    task = TaskRecord(task_type="agent.workflow", description="Queued agent workflow")
    recovery = WorkflowRecoveryRepository(repository.database_path)
    workflow_id = recovery.create_run(
        request_digest,
        step_specs,
        task=task,
        owner_user_id=owner_user_id,
        submission=(owner_user_id, "/agent/workflows", submission_key, request_digest)
        if submission_key is not None else None,
    )
    try:
        input_metadata = inputs.store(str(workflow_id), owner_user_id, payload)
    except Exception:
        # Never leave an executable queued task if encrypted input persistence fails.
        recovery.fail_queued_run(workflow_id, error_code="workflow_input_persistence_failed")
        raise
    return {
        "workflow": recovery.get_run(workflow_id, owner_user_id=owner_user_id),
        "execution": None,
        "queue": {"status": "queued", "worker_dispatch": "pending"},
        "input_metadata": {
            "schema_version": input_metadata["schema_version"],
            "payload_digest": input_metadata["payload_digest"],
        },
    }


def dispatch_queued_workflow(
    repository: TaskRepository,
    task: TaskRecord,
    lease: WorkerLease,
    lease_lost: Event,
) -> dict[str, object]:
    """Execute one queued workflow under the generic worker's existing lease."""
    settings = get_settings()
    recovery = WorkflowRecoveryRepository(repository.database_path)
    with repository._connection() as connection:
        row = connection.execute(
            "SELECT workflow_id, owner_user_id, request_digest FROM workflow_runs WHERE task_id = ?",
            (str(task.task_id),),
        ).fetchone()
    if row is None or not row["owner_user_id"]:
        return {"_worker_task_status": "failed", "error_code": "workflow_record_missing"}
    workflow_id = UUID(row["workflow_id"])
    owner_user_id = row["owner_user_id"]
    try:
        payload = WorkflowExecutionInputRepository(
            repository.database_path, settings.workflow_input_encryption_key
        ).load(str(workflow_id), owner_user_id)
        request = AgentPlanRequest.model_validate(payload)
        if workflow_digest(request) != row["request_digest"]:
            raise ValueError("workflow_input_digest_mismatch")
        from mrhub.api.routes.models import build_model_router
        from mrhub.tools.builtins import build_tool_registry

        core = AgentCore(build_model_router(), build_tool_registry())
        plan = core.plan(request)
        if not plan.get("execution_ready"):
            raise ValueError("workflow_no_longer_execution_ready")
        expected: list[tuple[int, str, str]] = []
        for item in plan.get("steps", []):
            if not isinstance(item, dict):
                continue
            number = int(item["step"])
            if number == 1:
                expected.append((1, "provider_selection", "provider_selection"))
            else:
                tool = request.tools[number - 2]
                definition = core.tool_registry.get(tool.name)
                expected.append((
                    number,
                    "external_tool" if definition.external_side_effect else "safe_tool",
                    tool.name,
                ))
        stored = recovery.get_run(workflow_id, owner_user_id=owner_user_id)
        if stored is None:
            raise LookupError("workflow_not_found")
        actual = [
            (int(step["step_number"]), str(step["step_kind"]), str(step["step_name"]))
            for step in stored["steps"]
        ]
        if expected != actual:
            raise ValueError("workflow_definition_changed")
    except (ExecutionInputUnavailable, LookupError, ValueError, TypeError):
        return {
            "_worker_task_status": "failed",
            "workflow_status": "failed",
            "error_code": "workflow_input_unavailable",
        }

    attempts: dict[int, StepAttempt] = {}
    needs_review = False
    try:
        decision = recovery.resume_decision(
            workflow_id, row["request_digest"], owner_user_id=owner_user_id
        )
        if decision.decision not in {"resume", "finish"}:
            raise ValueError("workflow_not_resumable")
        if lease_lost.is_set():
            raise RuntimeError("worker_lease_lost")
        recovery.start_run(workflow_id, lease=lease)
        start_step = decision.next_step or 2
        if decision.decision == "finish":
            return {
                "_worker_task_status": "succeeded",
                "workflow_id": str(workflow_id),
                "execution_completed": True,
                "executed_tool_count": 0,
            }
        if start_step == 1:
            provider_attempt = recovery.start_step(workflow_id, 1, lease=lease)
            provider_bytes = json.dumps(
                plan.get("selected_provider", {}), sort_keys=True, separators=(",", ":")
            ).encode()
            recovery.complete_step(
                workflow_id, provider_attempt, hashlib.sha256(provider_bytes).hexdigest(),
                lease=lease,
            )
            start_step = 2

        def ensure_active() -> None:
            if lease_lost.is_set():
                raise RuntimeError("worker_lease_lost")
            current = repository.get(task.task_id)
            if current is None or current.status is not TaskStatus.RUNNING:
                raise RuntimeError("workflow_cancel_requested")

        def on_step(number: int, status: str, error_code: str | None) -> None:
            nonlocal needs_review
            ensure_active()
            if status == "running":
                attempts[number] = recovery.start_step(workflow_id, number, lease=lease)
            elif status == "failed" and number in attempts:
                tool = request.tools[number - 2]
                definition = core.tool_registry.get(tool.name)
                needs_review = needs_review or definition.external_side_effect
                recovery.fail_step(
                    workflow_id,
                    attempts.pop(number),
                    error_code or "tool_execution_failed",
                    unknown_outcome=definition.external_side_effect,
                    lease=lease,
                    defer_terminal=True,
                )

        def on_step_result(number: int, output_digest: str) -> None:
            ensure_active()
            attempt = attempts.pop(number, None)
            if attempt is None:
                raise RuntimeError("workflow_step_attempt_missing")
            recovery.complete_step(workflow_id, attempt, output_digest, lease=lease)

        execution = core.execute(
            request, on_step=on_step, on_step_result=on_step_result, start_step=start_step
        )
        current = recovery.get_run(workflow_id, owner_user_id=owner_user_id)
        if execution.get("execution_completed"):
            return {
                "_worker_task_status": "succeeded",
                "workflow_id": str(workflow_id),
                "execution_completed": True,
                "executed_tool_count": len(execution.get("results", [])),
            }
        status = "recovery_required" if needs_review else "failed"
        return {
            "_worker_task_status": "waiting_approval" if needs_review else "failed",
            "workflow_id": str(workflow_id),
            "workflow_status": status,
            "error_code": "workflow_step_failed",
        }
    except Exception as dispatch_error:  # noqa: BLE001
        logger.warning(
            "Workflow dispatch stopped (%s)", type(dispatch_error).__name__
        )
        current_task = repository.get(task.task_id)
        if current_task is not None and current_task.status in {
            TaskStatus.CANCELLED, TaskStatus.WAITING_APPROVAL
        }:
            try:
                workflow_status = recovery.cancel_run(
                    workflow_id, lease=lease, defer_terminal=True
                )
            except Exception as cancel_error:  # noqa: BLE001
                logger.warning(
                    "Workflow cancellation state could not be persisted (%s)",
                    type(cancel_error).__name__,
                )
                current = recovery.get_run(workflow_id, owner_user_id=owner_user_id)
                workflow_status = current["status"] if current else "failed"
            if workflow_status == "recovery_required":
                return {
                    "_worker_task_status": "waiting_approval",
                    "workflow_id": str(workflow_id),
                    "workflow_status": workflow_status,
                    "error_code": "cancel_external_outcome_unknown",
                }
            return {"_worker_task_status": "cancelled", "workflow_id": str(workflow_id)}
        if not lease_lost.is_set():
            try:
                recovery.mark_interrupted(
                    workflow_id, lease=lease, defer_terminal=True
                )
            except Exception as recovery_error:  # noqa: BLE001
                logger.warning(
                    "Workflow recovery update failed (%s)", type(recovery_error).__name__
                )
        current = recovery.get_run(workflow_id, owner_user_id=owner_user_id)
        step_statuses = {step["status"] for step in current["steps"]} if current else set()
        status = "recovery_required" if "unknown_outcome" in step_statuses else "paused"
        return {
            "_worker_task_status": "waiting_approval",
            "workflow_id": str(workflow_id),
            "workflow_status": status,
            "error_code": "workflow_interrupted",
        }



def queue_workflow_resume(
    repository: TaskRepository,
    core: AgentCore,
    workflow_id: UUID,
    request: AgentPlanRequest,
    owner_user_id: str,
) -> dict[str, object]:
    """Validate a resume request and requeue it; execution remains worker-owned."""
    recovery = WorkflowRecoveryRepository(repository.database_path)
    digest = workflow_digest(request)
    workflow = recovery.get_run(workflow_id, owner_user_id=owner_user_id)
    if workflow is None or workflow["task_id"] is None:
        raise LookupError("Workflow not found")
    stored_payload = WorkflowExecutionInputRepository(
        repository.database_path, get_settings().workflow_input_encryption_key
    ).load(str(workflow_id), owner_user_id)
    if workflow_digest(AgentPlanRequest.model_validate(stored_payload)) != digest:
        raise ValueError("Supplied inputs do not match the encrypted workflow input")
    plan = core.plan(request)
    if not plan.get("execution_ready") or not isinstance(plan.get("steps"), list):
        raise ValueError("Current request is not executable")
    expected: list[tuple[int, str, str]] = []
    for item in plan["steps"]:
        if not isinstance(item, dict):
            continue
        number = int(item["step"])
        if number == 1:
            expected.append((1, "provider_selection", "provider_selection"))
        else:
            tool = request.tools[number - 2]
            definition = core.tool_registry.get(tool.name)
            expected.append((
                number,
                "external_tool" if definition.external_side_effect else "safe_tool",
                tool.name,
            ))
    actual = [
        (int(step["step_number"]), str(step["step_kind"]), str(step["step_name"]))
        for step in workflow["steps"]
    ]
    if expected != actual:
        raise ValueError("Current workflow definition differs from stored steps")
    provider_step = next((step for step in workflow["steps"] if step["step_number"] == 1), None)
    if provider_step is not None and provider_step["status"] == "succeeded":
        provider_bytes = json.dumps(
            plan.get("selected_provider", {}), sort_keys=True, separators=(",", ":")
        ).encode()
        if provider_step["output_digest"] != hashlib.sha256(provider_bytes).hexdigest():
            raise ValueError("Selected provider changed; workflow must be replanned")
    decision = recovery.resume_decision(
        workflow_id, digest, owner_user_id=owner_user_id
    )
    if decision.decision not in {"resume", "finish"}:
        raise ValueError(f"Workflow cannot be resumed: {decision.decision}")
    queued = recovery.queue_resume(workflow_id, digest, owner_user_id=owner_user_id)
    return {
        "workflow": queued,
        "execution": None,
        "queue": {"status": "queued", "worker_dispatch": "pending"},
        "resume_decision": decision.decision,
    }
