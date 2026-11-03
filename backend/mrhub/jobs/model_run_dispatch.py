"""Worker-owned execution for durable model-driven Agent runs."""

from __future__ import annotations

import hashlib
import json
from threading import Event
from uuid import UUID

from mrhub.agents.orchestrator import AgentLoopRequest, AgentOrchestrator
from mrhub.api.routes.models import build_model_router
from mrhub.domain.tasks import TaskRecord, TaskStatus
from mrhub.infrastructure.database import TaskRepository
from mrhub.jobs.engine import JobEngine
from mrhub.jobs.leases import WorkerLease
from mrhub.jobs.payload_envelope import (
    EncryptedPayload,
    PayloadEnvelopeError,
    decrypt_payload,
    encrypt_payload,
    load_payload_key,
)
from mrhub.jobs.recovery import WorkflowRecoveryError, WorkflowRecoveryRepository
from mrhub.tools.builtins import build_tool_registry


class ModelRunWorkerHandler:
    """Execute exactly one non-replayable model/tool loop under a fenced lease."""

    def __init__(self, repository: TaskRepository) -> None:
        self.repository = repository
        self.recovery = WorkflowRecoveryRepository(repository.database_path)
        self.jobs = JobEngine(repository)

    def __call__(
        self, task: TaskRecord, *, lease: WorkerLease, lease_lost: Event
    ) -> dict[str, object]:
        with self.repository._connection() as connection:
            row = connection.execute(
                """SELECT workflow_id, owner_user_id, status
                   FROM workflow_runs WHERE task_id = ?""",
                (str(task.task_id),),
            ).fetchone()
        if row is None or not row["owner_user_id"]:
            self._fail_closed(task, lease)
            return {"execution_completed": False, "error_code": "workflow_unavailable"}

        workflow_id = UUID(row["workflow_id"])
        owner_user_id = str(row["owner_user_id"])
        try:
            stored = self.recovery.get_encrypted_payload(
                workflow_id, owner_user_id=owner_user_id
            )
            if stored is None or stored["task_id"] != str(task.task_id):
                raise PayloadEnvelopeError("Model run payload is missing")
            payload = decrypt_payload(
                EncryptedPayload(
                    version=int(stored["version"]),
                    nonce_b64=str(stored["nonce_b64"]),
                    ciphertext_b64=str(stored["ciphertext_b64"]),
                ),
                workflow_id=str(workflow_id),
                task_id=str(task.task_id),
                owner_user_id=owner_user_id,
                key=load_payload_key(),
            )
            if payload.get("kind") != "agent.model_run.request":
                raise PayloadEnvelopeError("Model run payload kind is invalid")
            request_data = payload["request"]
            evidence = payload["evidence"]
            provider_mode = request_data["provider_mode"]
            request = AgentLoopRequest(
                goal=request_data["goal"],
                retrieved_context=evidence,
                prefer_local=provider_mode == "local",
                max_turns=request_data["max_turns"],
                max_output_tokens=request_data["max_output_tokens"],
            )
        except (PayloadEnvelopeError, KeyError, TypeError, ValueError):
            self._fail_closed(task, lease)
            return {"workflow_id": str(workflow_id), "execution_completed": False,
                    "error_code": "encrypted_payload_unavailable"}

        if lease_lost.is_set():
            return {"workflow_id": str(workflow_id), "execution_completed": False,
                    "error_code": "worker_lease_lost"}

        try:
            self.recovery.start_run(workflow_id, lease=lease)
            attempt = self.recovery.start_step(workflow_id, 1, lease=lease)
        except (WorkflowRecoveryError, LookupError):
            self._fail_closed(task, lease)
            return {
                "workflow_id": str(workflow_id),
                "execution_completed": False,
                "error_code": "workflow_not_dispatchable",
            }

        try:
            model_router = build_model_router(
                provider_mode=provider_mode,
                include_stub=False,
                max_timeout_seconds=30.0,
            )
            orchestrator = AgentOrchestrator(model_router, build_tool_registry())
        except Exception:
            self.recovery.fail_step(
                workflow_id, attempt, "model_setup_failed", lease=lease
            )
            with self.repository._connection() as connection:
                connection.execute(
                    """UPDATE idempotency_records SET status = 'failed'
                       WHERE task_id = ? AND status = 'running'""",
                    (str(task.task_id),),
                )
            current = self.jobs.get(task.task_id)
            if current is not None and current.status is TaskStatus.RUNNING:
                self.jobs.transition(task.task_id, TaskStatus.FAILED, lease=lease)
            return {
                "workflow_id": str(workflow_id),
                "execution_completed": False,
                "error_code": "model_setup_failed",
            }

        def should_cancel() -> bool:
            if lease_lost.is_set():
                return True
            with self.repository._connection() as connection:
                execution = connection.execute(
                    "SELECT error_code FROM worker_executions WHERE task_id = ?",
                    (str(task.task_id),),
                ).fetchone()
            return bool(execution and execution["error_code"] == "cancellation_requested")

        try:
            result = orchestrator.run(request, should_cancel=should_cancel)
            if should_cancel() and result.get("status") != "cancelled":
                result = {**result, "status": "cancelled", "error_code": "cancelled"}
        except Exception:
            # The inference/tool loop may have partially completed. Never replay it.
            self.recovery.mark_interrupted(workflow_id, lease=lease)
            with self.repository._connection() as connection:
                connection.execute(
                    """UPDATE idempotency_records SET status = 'unknown_outcome'
                       WHERE task_id = ? AND status = 'running'""",
                    (str(task.task_id),),
                )
            current = self.jobs.get(task.task_id)
            if current is not None and current.status is TaskStatus.RUNNING:
                self.jobs.transition(task.task_id, TaskStatus.WAITING_APPROVAL, lease=lease)
            return {"workflow_id": str(workflow_id), "execution_completed": False,
                    "error_code": "model_run_outcome_unknown"}

        if lease_lost.is_set():
            return {"workflow_id": str(workflow_id), "execution_completed": False,
                    "error_code": "worker_lease_lost"}

        output = {
            "kind": "agent.model_run.result",
            "provider_mode": provider_mode,
            "context_sources": payload.get("context_sources", []),
            "context_summary": payload.get("context_summary", {}),
            "execution": result,
        }
        try:
            encrypted = encrypt_payload(
                output,
                workflow_id=str(workflow_id),
                task_id=str(task.task_id),
                owner_user_id=owner_user_id,
                key=load_payload_key(),
            )
            replaced = self.recovery.replace_encrypted_payload(
                workflow_id,
                owner_user_id=owner_user_id,
                task_id=str(task.task_id),
                payload_envelope={
                    "version": encrypted.version,
                    "nonce_b64": encrypted.nonce_b64,
                    "ciphertext_b64": encrypted.ciphertext_b64,
                },
            )
            if not replaced:
                raise PayloadEnvelopeError("Encrypted model-run result could not be stored")
        except Exception:
            # A completed model/tool loop whose result cannot be durably stored
            # is ambiguous to callers and must never be replayed automatically.
            self.recovery.mark_interrupted(workflow_id, lease=lease)
            with self.repository._connection() as connection:
                connection.execute(
                    """UPDATE idempotency_records SET status = 'unknown_outcome'
                       WHERE task_id = ? AND status = 'running'""",
                    (str(task.task_id),),
                )
            current = self.jobs.get(task.task_id)
            if current is not None and current.status is TaskStatus.RUNNING:
                self.jobs.transition(
                    task.task_id, TaskStatus.WAITING_APPROVAL, lease=lease
                )
            return {
                "workflow_id": str(workflow_id),
                "execution_completed": False,
                "error_code": "model_run_result_persistence_unknown",
            }
        output_digest = hashlib.sha256(
            json.dumps(output, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        if result.get("status") == "cancelled":
            self.recovery.finish_run(workflow_id, "cancelled", lease=lease)
            current = self.jobs.get(task.task_id)
            if current is not None and current.status is TaskStatus.RUNNING:
                self.jobs.transition(task.task_id, TaskStatus.CANCELLED, lease=lease)
        else:
            self.recovery.complete_step(workflow_id, attempt, output_digest, lease=lease)
            self.recovery.finish_run(workflow_id, "succeeded", lease=lease)
            current = self.jobs.get(task.task_id)
            if current is not None and current.status is TaskStatus.RUNNING:
                self.jobs.transition(task.task_id, TaskStatus.SUCCEEDED, lease=lease)
        return {
            "workflow_id": str(workflow_id),
            "execution_completed": result.get("status") == "completed",
            "execution_status": result.get("status"),
            "turns": result.get("turns"),
            "tool_calls": result.get("tool_calls"),
        }

    def _fail_closed(self, task: TaskRecord, lease: WorkerLease) -> None:
        with self.repository._connection() as connection:
            row = connection.execute(
                "SELECT workflow_id, status FROM workflow_runs WHERE task_id = ?",
                (str(task.task_id),),
            ).fetchone()
        if row is not None and row["status"] in {"queued", "paused"}:
            workflow_id = UUID(row["workflow_id"])
            self.recovery.start_run(workflow_id, lease=lease)
            self.recovery.finish_run(workflow_id, "failed", lease=lease)
        current = self.jobs.get(task.task_id)
        if current is not None and current.status is TaskStatus.RUNNING:
            self.jobs.transition(task.task_id, TaskStatus.FAILED, lease=lease)
        with self.repository._connection() as connection:
            connection.execute(
                """UPDATE idempotency_records SET status = 'failed'
                   WHERE task_id = ? AND status IN ('accepted', 'running')""",
                (str(task.task_id),),
            )
