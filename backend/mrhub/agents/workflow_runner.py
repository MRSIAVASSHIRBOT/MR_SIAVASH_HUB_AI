"""Leased request-scoped workflow runner backed by durable Job state."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from threading import Event, Thread
from uuid import uuid4

from mrhub.agents.core import AgentCore, AgentPlanRequest
from mrhub.domain.tasks import TaskRecord, TaskStatus
from mrhub.infrastructure.database import TaskRepository
from mrhub.jobs.engine import JobEngine
from mrhub.jobs.leases import LeaseManager, WorkerLease
from mrhub.jobs.recovery import StepAttempt, WorkflowRecoveryRepository
from mrhub.security.audit import AuditLogger


class AgentWorkflowRunner:
    """Run supplied inputs in memory while fencing every durable workflow transition."""

    def __init__(
        self,
        repository: TaskRepository,
        core: AgentCore,
        *,
        lease_seconds: int = 60,
    ) -> None:
        self.repository = repository
        self.core = core
        self.jobs = JobEngine(repository)
        self.recovery = WorkflowRecoveryRepository(repository.database_path)
        self.lease_seconds = lease_seconds
        self.lease_manager = LeaseManager(
            repository.database_path, lease_seconds=lease_seconds
        )
        self.worker_id = str(uuid4())

    @staticmethod
    def _digest(value: object) -> str:
        encoded = json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
        return hashlib.sha256(encoded).hexdigest()

    def _heartbeat_loop(self, lease: WorkerLease, stop: Event, lost: Event) -> None:
        interval = max(0.1, self.lease_seconds / 3)
        while not stop.wait(interval):
            if self.lease_manager.heartbeat(lease) is None:
                lost.set()
                return

    def _record_execution_start(self, lease: WorkerLease) -> None:
        now = datetime.now(UTC).isoformat()
        with self.repository._connection() as connection:
            cursor = connection.execute(
                """
                UPDATE worker_executions
                SET attempt_count = attempt_count + 1, started_at = ?,
                    finished_at = NULL, result_json = NULL, error_code = NULL
                WHERE task_id = ? AND lease_owner = ? AND execution_token = ?
                  AND lease_expires_at > ?
                """,
                (now, lease.task_id, lease.owner, lease.fencing_token, now),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("Workflow lease was lost before execution began")

    def execute(
        self,
        request: AgentPlanRequest,
        plan: dict[str, object],
        request_digest: str,
        owner_user_id: str,
    ) -> dict[str, object]:
        """Create a linked Job/Workflow and execute each validated step in order."""
        raw_steps = plan.get("steps", [])
        if not isinstance(raw_steps, list) or not raw_steps:
            raise ValueError("Workflow plan contains no executable steps")
        step_specs = []
        for step in raw_steps:
            if not isinstance(step, dict):
                continue
            number = int(step["step"])
            if number == 1:
                kind = "provider_selection"
                name = "provider_selection"
            else:
                requested_tool = request.tools[number - 2]
                definition = self.core.tool_registry.get(requested_tool.name)
                kind = "external_tool" if definition.external_side_effect else "safe_tool"
                name = requested_tool.name
            step_specs.append(
                {"step_number": number, "kind": kind, "name": name}
            )
        task = TaskRecord(
            task_type="agent.workflow",
            description="Agent workflow execution",
        )
        workflow_id = self.recovery.create_run(
            request_digest,
            step_specs,
            task=task,
            owner_user_id=owner_user_id,
        )
        AuditLogger(self.repository).record(
            event_type="task.submitted",
            outcome="queued",
            subject_id=str(task.task_id),
            metadata={
                "task_type": task.task_type,
                "risk_class": task.risk_class.value,
                "decision": "allow",
            },
        )
        self.jobs.transition(task.task_id, TaskStatus.RUNNING)
        lease = self.lease_manager.acquire(str(task.task_id), self.worker_id)
        if lease is None:
            raise RuntimeError("Workflow task could not acquire its execution lease")
        stop_heartbeat = Event()
        lease_lost = Event()
        heartbeat = Thread(
            target=self._heartbeat_loop,
            args=(lease, stop_heartbeat, lease_lost),
            name=f"agent-workflow-lease-{workflow_id}",
            daemon=True,
        )
        heartbeat.start()
        attempts: dict[int, StepAttempt] = {}

        try:
            self._record_execution_start(lease)
            self.recovery.start_run(workflow_id, lease=lease)
            provider_attempt = self.recovery.start_step(workflow_id, 1, lease=lease)
            provider_digest = self._digest(plan.get("selected_provider", {}))
            self.recovery.complete_step(
                workflow_id, provider_attempt, provider_digest, lease=lease
            )

            def on_step(number: int, status: str, error_code: str | None) -> None:
                if lease_lost.is_set():
                    raise RuntimeError("Workflow worker lease was lost")
                if status == "running":
                    attempts[number] = self.recovery.start_step(
                        workflow_id, number, lease=lease
                    )
                elif status == "failed":
                    attempt = attempts.get(number)
                    if attempt is not None:
                        requested_tool = request.tools[number - 2]
                        definition = self.core.tool_registry.get(requested_tool.name)
                        self.recovery.fail_step(
                            workflow_id,
                            attempt,
                            error_code or "tool_execution_failed",
                            unknown_outcome=definition.external_side_effect,
                            lease=lease,
                        )

            def on_step_result(number: int, output_digest: str) -> None:
                if lease_lost.is_set():
                    raise RuntimeError("Workflow worker lease was lost")
                attempt = attempts.get(number)
                if attempt is None:
                    raise RuntimeError("Workflow step result has no active attempt")
                self.recovery.complete_step(
                    workflow_id, attempt, output_digest, lease=lease
                )
                del attempts[number]

            execution = self.core.execute(
                request,
                on_step=on_step,
                on_step_result=on_step_result,
            )
            current = self.recovery.get_run(workflow_id)
            if execution["execution_completed"]:
                self.recovery.finish_run(workflow_id, "succeeded", lease=lease)
                self.jobs.transition(task.task_id, TaskStatus.SUCCEEDED, lease=lease)
            else:
                if current is not None and current["status"] == "running":
                    self.recovery.finish_run(workflow_id, "failed", lease=lease)
                    current = self.recovery.get_run(workflow_id)
                target = (
                    TaskStatus.WAITING_APPROVAL
                    if current is not None and current["status"] == "recovery_required"
                    else TaskStatus.FAILED
                )
                self.jobs.transition(task.task_id, target, lease=lease)
        except Exception as exc:
            if self.lease_manager.is_current(lease):
                self.recovery.mark_interrupted(workflow_id, lease=lease)
                current = self.recovery.get_run(workflow_id)
                if current is not None and current["status"] == "running":
                    self.recovery.finish_run(workflow_id, "failed", lease=lease)
                    current = self.recovery.get_run(workflow_id)
                task_state = self.jobs.get(task.task_id)
                if task_state is not None and task_state.status is TaskStatus.RUNNING:
                    target = (
                        TaskStatus.WAITING_APPROVAL
                        if current is not None and current["status"] == "recovery_required"
                        else TaskStatus.FAILED
                    )
                    self.jobs.transition(task.task_id, target, lease=lease)
            raise RuntimeError("Workflow execution stopped; inspect its recovery state") from exc
        finally:
            stop_heartbeat.set()
            heartbeat.join(timeout=max(1.0, self.lease_seconds))
            self.lease_manager.release(lease)

        return {
            "workflow": self.recovery.get_run(workflow_id),
            "execution": {
                "execution_completed": execution["execution_completed"],
                "model_inference_started": execution["model_inference_started"],
                "tools_executed": execution["tools_executed"],
                "error_code": execution.get("error_code"),
                "executed_tool_count": len(execution["results"]),
            },
        }
