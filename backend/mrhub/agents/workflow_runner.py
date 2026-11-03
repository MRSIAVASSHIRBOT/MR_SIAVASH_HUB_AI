"""Leased request-scoped workflow runner backed by durable Job state."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from threading import Event, Thread
from uuid import UUID, uuid4

from mrhub.agents.core import AgentCore, AgentPlanRequest
from mrhub.domain.tasks import TaskRecord, TaskStatus
from mrhub.infrastructure.database import TaskRepository
from mrhub.jobs.engine import JobEngine
from mrhub.jobs.leases import LeaseError, LeaseManager, WorkerLease
from mrhub.jobs.recovery import ResumeDecision, StepAttempt, WorkflowRecoveryRepository
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
            try:
                renewed = self.lease_manager.heartbeat(lease)
            except (sqlite3.Error, LeaseError):
                # A heartbeat failure means lease ownership cannot be confirmed.
                lost.set()
                return
            if renewed is None:
                lost.set()
                return

    def _record_execution_start(
        self, lease: WorkerLease, *, increment_attempt: bool = True
    ) -> None:
        now = datetime.now(UTC).isoformat()
        with self.repository._connection() as connection:
            cursor = connection.execute(
                """
                UPDATE worker_executions
                SET attempt_count = attempt_count + ?, started_at = ?,
                    finished_at = NULL, result_json = NULL, error_code = NULL
                WHERE task_id = ? AND lease_owner = ? AND execution_token = ?
                  AND lease_expires_at > ?
                """,
                (
                    1 if increment_attempt else 0,
                    now,
                    lease.task_id,
                    lease.owner,
                    lease.fencing_token,
                    now,
                ),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("Workflow lease was lost before execution began")

    def execute(
        self,
        request: AgentPlanRequest,
        plan: dict[str, object],
        request_digest: str,
        owner_user_id: str,
        *,
        workflow_id: UUID | None = None,
        task: TaskRecord | None = None,
        lease: WorkerLease | None = None,
        lease_lost: Event | None = None,
    ) -> dict[str, object]:
        """Execute under either a local lease or a WorkerEngine-owned lease.

        Worker dispatch must reuse its existing task, workflow, and lease instead
        of creating duplicate durable state or competing lease heartbeats.
        """
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
        worker_owned_lease = lease is not None
        if worker_owned_lease:
            if workflow_id is None or task is None or lease_lost is None:
                raise ValueError(
                    "Worker execution requires workflow_id, task, lease, and lease_lost"
                )
            if str(task.task_id) != lease.task_id:
                raise ValueError("Worker lease does not match the workflow task")
            stored = self.recovery.get_run(workflow_id, owner_user_id=owner_user_id)
            if stored is None or stored.get("task_id") != str(task.task_id):
                raise LookupError("Queued workflow not found for this task owner")
            stop_heartbeat = Event()
        else:
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
            self._record_execution_start(
                lease, increment_attempt=not worker_owned_lease
            )
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

            def should_cancel() -> bool:
                # Lease loss is not user cancellation: a stale worker must stop
                # without finalizing state owned by the successor.
                if lease_lost.is_set():
                    raise RuntimeError("Workflow worker lease was lost")
                current_task = self.jobs.get(task.task_id)
                if current_task is None or current_task.status is TaskStatus.CANCELLED:
                    return True
                with self.repository._connection() as connection:
                    row = connection.execute(
                        "SELECT error_code FROM worker_executions WHERE task_id = ?",
                        (str(task.task_id),),
                    ).fetchone()
                return row is not None and row["error_code"] == "cancellation_requested"

            execution = self.core.execute(
                request,
                on_step=on_step,
                on_step_result=on_step_result,
                should_cancel=should_cancel,
            )
            # Close the race between the final in-loop cancellation check and
            # workflow finalization, including workflows with zero tool steps.
            if not execution.get("cancelled") and should_cancel():
                execution = {
                    **execution,
                    "cancelled": True,
                    "execution_completed": False,
                    "error_code": "cancelled",
                }
            current = self.recovery.get_run(workflow_id)
            if execution.get("cancelled"):
                if current is not None and current["status"] == "running":
                    self.recovery.finish_run(workflow_id, "cancelled", lease=lease)
                current_task = self.jobs.get(task.task_id)
                if current_task is not None and current_task.status is TaskStatus.RUNNING:
                    self.jobs.transition(task.task_id, TaskStatus.CANCELLED, lease=lease)
                return {
                    "workflow_id": str(workflow_id),
                    "execution": execution,
                }
            if execution["execution_completed"]:
                self.recovery.finish_run(workflow_id, "succeeded", lease=lease)
                self.jobs.transition(task.task_id, TaskStatus.SUCCEEDED, lease=lease)
            else:
                if current is not None and current["status"] == "running":
                    self.recovery.finish_run(workflow_id, "failed", lease=lease)
                    current = self.recovery.get_run(workflow_id)
                target = (
                    TaskStatus.WAITING_APPROVAL
                    if current is not None and current["status"] in {"recovery_required", "paused"}
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
                        if current is not None and current["status"] in {"recovery_required", "paused"}
                        else TaskStatus.FAILED
                    )
                    self.jobs.transition(task.task_id, target, lease=lease)
            raise RuntimeError("Workflow execution stopped; inspect its recovery state") from exc
        finally:
            if not worker_owned_lease:
                stop_heartbeat.set()
                heartbeat.join(timeout=max(1.0, self.lease_seconds))
                self.lease_manager.release(lease)

        return {
            "workflow": self.recovery.get_run(workflow_id, owner_user_id=owner_user_id),
            "execution": {
                "execution_completed": execution["execution_completed"],
                "model_inference_started": execution["model_inference_started"],
                "tools_executed": execution["tools_executed"],
                "error_code": execution.get("error_code"),
                "executed_tool_count": len(execution["results"]),
            },
        }


    def _validate_resume(
        self,
        workflow_id: UUID,
        request: AgentPlanRequest,
        plan: dict[str, object],
        request_digest: str,
        owner_user_id: str,
        *,
        task: TaskRecord | None = None,
    ) -> tuple[dict[str, object], ResumeDecision, UUID]:
        """Validate owner, request, plan, and job state without executing work."""
        workflow = self.recovery.get_run(workflow_id, owner_user_id=owner_user_id)
        if workflow is None or workflow["task_id"] is None:
            raise LookupError("Workflow not found")
        decision = self.recovery.resume_decision(
            workflow_id, request_digest, owner_user_id=owner_user_id
        )
        if decision.decision not in {"resume", "finish"} or (
            decision.decision == "resume" and decision.next_step is None
        ):
            raise ValueError(f"Workflow is not resumable: {decision.decision}")

        raw_steps = plan.get("steps", [])
        if not plan.get("execution_ready") or not isinstance(raw_steps, list):
            raise ValueError("Current request is not executable")
        expected = []
        for item in raw_steps:
            if not isinstance(item, dict):
                continue
            number = int(item["step"])
            if number == 1:
                expected.append((1, "provider_selection", "provider_selection"))
            else:
                tool = request.tools[number - 2]
                definition = self.core.tool_registry.get(tool.name)
                kind = "external_tool" if definition.external_side_effect else "safe_tool"
                expected.append((number, kind, tool.name))
        stored = [
            (int(step["step_number"]), step["step_kind"], step["step_name"])
            for step in workflow["steps"]
        ]
        if expected != stored:
            raise ValueError("Current workflow plan differs from the stored definition")

        provider_step = next(
            (step for step in workflow["steps"] if step["step_number"] == 1), None
        )
        if (
            provider_step is not None
            and provider_step["status"] == "succeeded"
            and provider_step["output_digest"]
            != self._digest(plan.get("selected_provider", {}))
        ):
            raise ValueError("Selected provider changed; workflow must be replanned")

        task_id = UUID(str(workflow["task_id"]))
        task_state = self.jobs.get(task_id)
        expected_status = TaskStatus.RUNNING if task is not None else TaskStatus.WAITING_APPROVAL
        if (
            task_state is None
            or task_state.status is not expected_status
            or (task is not None and task.task_id != task_id)
        ):
            raise ValueError("Linked job is not in the expected resume state")
        return workflow, decision, task_id

    def queue_resume(
        self,
        workflow_id: UUID,
        request: AgentPlanRequest,
        plan: dict[str, object],
        request_digest: str,
        owner_user_id: str,
    ) -> dict[str, object]:
        """Validate and enqueue a resume without running workflow steps in the API."""
        _workflow, _decision, task_id = self._validate_resume(
            workflow_id, request, plan, request_digest, owner_user_id
        )
        self.recovery.queue_resume(
            workflow_id,
            owner_user_id=owner_user_id,
            request_digest=request_digest,
        )
        AuditLogger(self.repository).record(
            event_type="workflow.resume_queued",
            outcome="queued",
            subject_id=str(task_id),
            metadata={"workflow_id": str(workflow_id), "task_type": "agent.workflow"},
        )
        return {
            "workflow": self.recovery.get_run(
                workflow_id, owner_user_id=owner_user_id
            ),
            "execution": None,
            "queued": True,
        }

    def resume(
        self,
        workflow_id: UUID,
        request: AgentPlanRequest,
        plan: dict[str, object],
        request_digest: str,
        owner_user_id: str,
        *,
        task: TaskRecord | None = None,
        lease: WorkerLease | None = None,
        lease_lost: Event | None = None,
    ) -> dict[str, object]:
        """Resume a workflow under the pull worker's lease, or a local lease for tests."""
        worker_owned_lease = lease is not None
        _workflow, decision, task_id = self._validate_resume(
            workflow_id,
            request,
            plan,
            request_digest,
            owner_user_id,
            task=task if worker_owned_lease else None,
        )
        if worker_owned_lease:
            if task is None or lease_lost is None or lease.task_id != str(task_id):
                raise ValueError("Worker-owned resume requires its task and lease-loss signal")
            if lease_lost.is_set():
                raise RuntimeError("Workflow worker lease was lost")
            stop_heartbeat = None
            heartbeat = None
        else:
            if task is not None or lease_lost is not None:
                raise ValueError("A task or lease-loss signal requires a worker-owned lease")
            self.jobs.transition(task_id, TaskStatus.QUEUED)
            self.jobs.transition(task_id, TaskStatus.RUNNING)
            lease = self.lease_manager.acquire(str(task_id), self.worker_id)
            if lease is None:
                self.jobs.transition(task_id, TaskStatus.WAITING_APPROVAL)
                raise RuntimeError("Workflow task could not acquire its execution lease")
            stop_heartbeat = Event()
            lease_lost = Event()
            heartbeat = Thread(
                target=self._heartbeat_loop,
                args=(lease, stop_heartbeat, lease_lost),
                name=f"agent-workflow-resume-{workflow_id}",
                daemon=True,
            )
            heartbeat.start()

        assert lease is not None and lease_lost is not None
        attempts: dict[int, StepAttempt] = {}
        try:
            self._record_execution_start(lease, increment_attempt=not worker_owned_lease)
            self.recovery.start_run(workflow_id, lease=lease)

            def should_cancel() -> bool:
                if lease_lost.is_set():
                    raise RuntimeError("Workflow worker lease was lost")
                current_task = self.jobs.get(task_id)
                if current_task is None or current_task.status is TaskStatus.CANCELLED:
                    return True
                with self.repository._connection() as connection:
                    row = connection.execute(
                        "SELECT error_code FROM worker_executions WHERE task_id = ?",
                        (str(task_id),),
                    ).fetchone()
                return row is not None and row["error_code"] == "cancellation_requested"

            if decision.decision == "finish":
                execution = {
                    "execution_completed": True,
                    "model_inference_started": False,
                    "tools_executed": False,
                    "error_code": None,
                    "results": [],
                }
            else:
                start_step = decision.next_step
                if start_step == 1:
                    provider_attempt = self.recovery.start_step(
                        workflow_id, 1, lease=lease
                    )
                    self.recovery.complete_step(
                        workflow_id,
                        provider_attempt,
                        self._digest(plan.get("selected_provider", {})),
                        lease=lease,
                    )
                    start_step = 2

                def on_step(
                    number: int, status: str, error_code: str | None
                ) -> None:
                    if lease_lost.is_set():
                        raise RuntimeError("Workflow worker lease was lost")
                    if status == "running":
                        attempts[number] = self.recovery.start_step(
                            workflow_id, number, lease=lease
                        )
                    elif status == "failed":
                        attempt = attempts.get(number)
                        if attempt is not None:
                            definition = self.core.tool_registry.get(
                                request.tools[number - 2].name
                            )
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
                    start_step=start_step,
                    should_cancel=should_cancel,
                )

            if not execution.get("cancelled") and should_cancel():
                execution = {
                    **execution,
                    "cancelled": True,
                    "execution_completed": False,
                    "error_code": "cancelled",
                }

            current = self.recovery.get_run(
                workflow_id, owner_user_id=owner_user_id
            )
            if execution.get("cancelled"):
                if current is not None and current["status"] == "running":
                    self.recovery.finish_run(workflow_id, "cancelled", lease=lease)
                current_task = self.jobs.get(task_id)
                if current_task is not None and current_task.status is TaskStatus.RUNNING:
                    self.jobs.transition(task_id, TaskStatus.CANCELLED, lease=lease)
            elif execution["execution_completed"]:
                self.recovery.finish_run(workflow_id, "succeeded", lease=lease)
                self.jobs.transition(task_id, TaskStatus.SUCCEEDED, lease=lease)
            else:
                if current is not None and current["status"] == "running":
                    self.recovery.finish_run(workflow_id, "failed", lease=lease)
                current = self.recovery.get_run(
                    workflow_id, owner_user_id=owner_user_id
                )
                target = (
                    TaskStatus.WAITING_APPROVAL
                    if current is not None
                    and current["status"] in {"recovery_required", "paused"}
                    else TaskStatus.FAILED
                )
                self.jobs.transition(task_id, target, lease=lease)
        except Exception as exc:
            if self.lease_manager.is_current(lease):
                self.recovery.mark_interrupted(workflow_id, lease=lease)
                current = self.recovery.get_run(
                    workflow_id, owner_user_id=owner_user_id
                )
                if current is not None and current["status"] == "running":
                    self.recovery.finish_run(workflow_id, "failed", lease=lease)
                    current = self.recovery.get_run(
                        workflow_id, owner_user_id=owner_user_id
                    )
                state = self.jobs.get(task_id)
                if state is not None and state.status is TaskStatus.RUNNING:
                    target = (
                        TaskStatus.WAITING_APPROVAL
                        if current is not None
                        and current["status"] in {"recovery_required", "paused"}
                        else TaskStatus.FAILED
                    )
                    self.jobs.transition(task_id, target, lease=lease)
            raise RuntimeError("Workflow resume stopped; inspect its recovery state") from exc
        finally:
            if not worker_owned_lease:
                assert stop_heartbeat is not None and heartbeat is not None
                stop_heartbeat.set()
                heartbeat.join(timeout=max(1.0, self.lease_seconds))
                self.lease_manager.release(lease)

        return {
            "workflow": self.recovery.get_run(
                workflow_id, owner_user_id=owner_user_id
            ),
            "execution": {
                "execution_completed": execution["execution_completed"],
                "model_inference_started": execution["model_inference_started"],
                "tools_executed": execution["tools_executed"],
                "error_code": execution.get("error_code"),
                "executed_tool_count": len(execution["results"]),
            },
        }
