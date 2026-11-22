"""Worker-owned dispatch for durable, encrypted agent workflows."""
from __future__ import annotations

import hmac
import sqlite3
from threading import Event
from uuid import UUID

from pydantic import ValidationError

from mrhub.agents.awi_planner import ExecutionPlan
from mrhub.agents.core import AgentCore, AgentPlanRequest
from mrhub.agents.plan_execution import (
    PLAN_EXECUTION_FORMAT,
    PlanExecutionBindingError,
    canonical_digest,
    validate_plan_bindings_against_snapshot,
    validate_plan_execution_payload,
)
from mrhub.agents.plan_repository import AgentWorkOrderPlanRepository
from mrhub.agents.work_order import WorkOrder
from mrhub.agents.workflow_runner import AgentWorkflowRunner
from mrhub.api.routes.models import build_model_router
from mrhub.domain.tasks import TaskRecord, TaskStatus
from mrhub.infrastructure.database import TaskRepository
from mrhub.jobs.engine import JobEngine
from mrhub.jobs.leases import WorkerLease
from mrhub.jobs.payload_envelope import (
    EncryptedPayload,
    PayloadEnvelopeError,
    decrypt_payload,
    decrypt_plan_payload,
    load_payload_key,
)
from mrhub.jobs.recovery import WorkflowRecoveryRepository
from mrhub.security.audit import AuditLogger
from mrhub.security.tool_permissions import ToolPermissionService
from mrhub.tools.builtins import build_tool_registry


class WorkflowWorkerHandler:
    """Decrypt and execute a queued workflow under the worker's existing lease."""

    def __init__(self, repository: TaskRepository) -> None:
        self.repository = repository
        self.recovery = WorkflowRecoveryRepository(repository.database_path)
        self.jobs = JobEngine(repository)

    def __call__(
        self, task: TaskRecord, *, lease: WorkerLease, lease_lost: Event
    ) -> dict[str, object]:
        with self.repository._connection() as connection:
            row = connection.execute(
                """
                SELECT workflow_id, owner_user_id, status, last_error_code
                FROM workflow_runs WHERE task_id = ?
                """,
                (str(task.task_id),),
            ).fetchone()
        if row is None:
            return self._fail_closed(task, lease, None, "workflow_payload_unavailable")
        workflow_id = UUID(row["workflow_id"])
        if not row["owner_user_id"]:
            return self._fail_closed(
                task, lease, workflow_id, "workflow_payload_unavailable"
            )
        owner_user_id = row["owner_user_id"]
        plan_binding: dict[str, object] | None = None
        persisted_request_digest: str | None = None

        def fail_closed(error_code: str) -> dict[str, object]:
            result = self._fail_closed(task, lease, workflow_id, error_code)
            if plan_binding is not None:
                current_workflow = self.recovery.get_run(
                    workflow_id,
                    owner_user_id=owner_user_id,
                )
                if current_workflow is not None and current_workflow["status"] in {
                    "succeeded",
                    "failed",
                    "cancelled",
                }:
                    try:
                        self.recovery.delete_encrypted_payload(
                            workflow_id,
                            owner_user_id=owner_user_id,
                        )
                        AgentWorkOrderPlanRepository(
                            self.repository.database_path
                        ).erase_consumed(
                            str(plan_binding["plan_id"]),
                            owner_user_id=owner_user_id,
                            workflow_id=str(workflow_id),
                        )
                    except sqlite3.Error:
                        result["payload_cleanup_pending"] = True
            return result

        permissions = ToolPermissionService(
            self.repository,
            AuditLogger(self.repository),
        )
        registry = None
        try:
            stored = self.recovery.get_encrypted_payload(
                workflow_id, owner_user_id=owner_user_id
            )
            if stored is None or stored["task_id"] != str(task.task_id):
                raise PayloadEnvelopeError("Workflow payload is missing")
            envelope = EncryptedPayload(
                version=int(stored["version"]),
                nonce_b64=str(stored["nonce_b64"]),
                ciphertext_b64=str(stored["ciphertext_b64"]),
            )
            payload = decrypt_payload(
                envelope,
                workflow_id=str(workflow_id),
                task_id=str(task.task_id),
                owner_user_id=owner_user_id,
                key=load_payload_key(),
            )
            if isinstance(payload, dict) and payload.get("format") == PLAN_EXECUTION_FORMAT:
                request, plan_binding = validate_plan_execution_payload(payload)
                plan_record = AgentWorkOrderPlanRepository(
                    self.repository.database_path
                ).get(
                    str(plan_binding["plan_id"]),
                    owner_user_id=owner_user_id,
                )
                if (
                    plan_record is None
                    or plan_record.status != "consumed"
                    or plan_record.workflow_id != str(workflow_id)
                    or plan_record.plan_digest != plan_binding["plan_digest"]
                ):
                    raise PlanExecutionBindingError(
                        "Consumed plan is not bound to this owner and workflow"
                    )
                stored_workflow = self.recovery.get_run(
                    workflow_id,
                    owner_user_id=owner_user_id,
                )
                if (
                    stored_workflow is None
                    or stored_workflow.get("request_digest")
                    != plan_binding["request_digest"]
                ):
                    raise PlanExecutionBindingError(
                        "Workflow request digest does not match its encrypted plan binding"
                    )
                persisted_request_digest = str(stored_workflow["request_digest"])
                stored_plan = decrypt_plan_payload(
                    plan_record.envelope,
                    plan_id=plan_record.plan_id,
                    owner_user_id=owner_user_id,
                    key=load_payload_key(),
                )
                if set(stored_plan) != {"work_order", "plan"}:
                    raise PlanExecutionBindingError("Consumed plan payload shape is invalid")
                work_order = WorkOrder.model_validate(stored_plan["work_order"])
                execution_plan = ExecutionPlan.model_validate(stored_plan["plan"])
                plan_digest = canonical_digest(
                    {
                        "work_order": work_order.model_dump(mode="json"),
                        "plan": execution_plan.model_dump(mode="json"),
                    }
                )
                if not hmac.compare_digest(plan_digest, plan_record.plan_digest):
                    raise PlanExecutionBindingError("Consumed plan digest failed verification")

                registry = build_tool_registry(owner_user_id=owner_user_id)
                current_permissions = permissions.active_permissions(owner_user_id)
                validate_plan_bindings_against_snapshot(
                    request=request,
                    binding=plan_binding,
                    work_order=work_order,
                    plan=execution_plan,
                    registry=registry,
                    granted_permissions=current_permissions,
                )
            else:
                request = AgentPlanRequest.model_validate(payload)
                registry = build_tool_registry()
        except (
            PayloadEnvelopeError,
            PlanExecutionBindingError,
            ValidationError,
            TypeError,
            ValueError,
            sqlite3.Error,
        ):
            return fail_closed("workflow_payload_unavailable")

        if lease_lost.is_set():
            return fail_closed("workflow_lease_lost")

        if registry is None:
            return fail_closed("workflow_tool_registry_unavailable")
        core = AgentCore(
            build_model_router(),
            registry,
            permission_provider=lambda: permissions.active_permissions(owner_user_id),
        )
        plan = core.plan(request)
        if not plan.get("execution_ready"):
            return fail_closed("workflow_plan_not_executable")
        runner = AgentWorkflowRunner(self.repository, core)
        request_digest = (
            persisted_request_digest
            if plan_binding is not None and persisted_request_digest is not None
            else AgentWorkflowRunner._digest(request.canonical_payload())
        )
        if row["status"] == "paused" and row["last_error_code"] == "resume_queued":
            try:
                result = runner.resume(
                    workflow_id,
                    request,
                    plan,
                    request_digest,
                    owner_user_id,
                    task=task,
                    lease=lease,
                    lease_lost=lease_lost,
                )
            except (LookupError, ValueError):
                return fail_closed("workflow_resume_validation_failed")
        elif row["status"] == "queued":
            result = runner.execute(
                request,
                plan,
                request_digest,
                owner_user_id,
                workflow_id=workflow_id,
                task=task,
                lease=lease,
                lease_lost=lease_lost,
            )
        else:
            return fail_closed("workflow_state_not_dispatchable")
        current = self.recovery.get_run(workflow_id, owner_user_id=owner_user_id)
        payload_cleanup_pending = False
        if current is not None and current["status"] in {"succeeded", "failed", "cancelled"}:
            try:
                self.recovery.delete_encrypted_payload(
                    workflow_id,
                    owner_user_id=owner_user_id,
                )
                if plan_binding is not None:
                    AgentWorkOrderPlanRepository(
                        self.repository.database_path
                    ).erase_consumed(
                        str(plan_binding["plan_id"]),
                        owner_user_id=owner_user_id,
                        workflow_id=str(workflow_id),
                    )
            except sqlite3.Error:
                # The workflow has reached a terminal state. Keep the result stable
                # and expose only that encrypted-payload cleanup needs reconciliation.
                payload_cleanup_pending = True
        execution = result.get("execution")
        if isinstance(execution, dict):
            return {
                "workflow_id": str(workflow_id),
                "execution_completed": bool(execution.get("execution_completed")),
                "executed_tool_count": int(execution.get("executed_tool_count", 0)),
                "model_inference_started": bool(execution.get("model_inference_started")),
                "tools_executed": bool(execution.get("tools_executed")),
                "error_code": execution.get("error_code"),
                "evaluation": execution.get("evaluation"),
                "evaluation_scope": execution.get("evaluation_scope"),
                "payload_cleanup_pending": payload_cleanup_pending,
            }
        return {
            "workflow_id": str(workflow_id),
            "execution_completed": False,
            "payload_cleanup_pending": payload_cleanup_pending,
        }

    def _fail_closed(
        self,
        task: TaskRecord,
        lease: WorkerLease,
        workflow_id: UUID | None,
        error_code: str,
    ) -> dict[str, object]:
        """Persist a sanitized failure without exposing payload or key material."""
        if workflow_id is not None and self.recovery.get_run(workflow_id) is not None:
            current = self.recovery.get_run(workflow_id)
            if current is not None and current["status"] in {"queued", "paused"}:
                self.recovery.start_run(workflow_id, lease=lease)
                self.recovery.finish_run(workflow_id, "failed", lease=lease)
        current_task = self.jobs.get(task.task_id)
        if current_task is not None and current_task.status is TaskStatus.RUNNING:
            self.jobs.transition(task.task_id, TaskStatus.FAILED, lease=lease)
        return {
            "workflow_id": str(workflow_id) if workflow_id else None,
            "execution_completed": False,
            "error_code": error_code,
        }
