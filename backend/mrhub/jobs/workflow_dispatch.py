"""Worker-owned dispatch for durable, encrypted agent workflows."""
from __future__ import annotations

from threading import Event
from uuid import UUID

from pydantic import ValidationError

from mrhub.agents.core import AgentCore, AgentPlanRequest
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
    load_payload_key,
)
from mrhub.jobs.recovery import WorkflowRecoveryRepository
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
            request = AgentPlanRequest.model_validate(payload)
        except (PayloadEnvelopeError, ValidationError, TypeError, ValueError):
            return self._fail_closed(
                task, lease, workflow_id, "workflow_payload_unavailable"
            )

        if lease_lost.is_set():
            return self._fail_closed(task, lease, workflow_id, "workflow_lease_lost")

        core = AgentCore(build_model_router(), build_tool_registry())
        plan = core.plan(request)
        if not plan.get("execution_ready"):
            return self._fail_closed(
                task, lease, workflow_id, "workflow_plan_not_executable"
            )
        runner = AgentWorkflowRunner(self.repository, core)
        request_digest = AgentWorkflowRunner._digest(request.model_dump(mode="json"))
        if row["status"] == "paused" and row["last_error_code"] == "resume_queued":
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
            return self._fail_closed(
                task, lease, workflow_id, "workflow_state_not_dispatchable"
            )
        current = self.recovery.get_run(workflow_id, owner_user_id=owner_user_id)
        if current is not None and current["status"] in {"succeeded", "failed", "cancelled"}:
            self.recovery.delete_encrypted_payload(
                workflow_id, owner_user_id=owner_user_id
            )
        execution = result.get("execution")
        if isinstance(execution, dict):
            return {
                "workflow_id": str(workflow_id),
                "execution_completed": bool(execution.get("execution_completed")),
                "executed_tool_count": int(execution.get("executed_tool_count", 0)),
                "model_inference_started": bool(execution.get("model_inference_started")),
                "tools_executed": bool(execution.get("tools_executed")),
                "error_code": execution.get("error_code"),
            }
        return {"workflow_id": str(workflow_id), "execution_completed": False}

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
