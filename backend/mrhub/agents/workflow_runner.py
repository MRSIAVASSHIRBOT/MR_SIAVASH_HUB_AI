"""Leased request-scoped workflow runner backed by durable Job state."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from logging import getLogger
from threading import Event, Thread
from uuid import UUID, uuid4

from mrhub.agents.core import AgentCore, AgentPlanRequest
from mrhub.agents.evaluation import (
    CriterionStatus,
    EvaluationCriterion,
    build_correction_plan,
    evaluate_criteria,
)
from mrhub.domain.tasks import TaskRecord, TaskStatus
from mrhub.infrastructure.database import TaskRepository
from mrhub.jobs.engine import JobEngine
from mrhub.jobs.leases import LeaseError, LeaseManager, WorkerLease
from mrhub.jobs.recovery import ResumeDecision, StepAttempt, WorkflowRecoveryRepository
from mrhub.security.audit import AuditLogger


class AgentWorkflowRunner:
    """Run supplied inputs in memory while fencing every durable workflow transition."""

    _logger = getLogger(__name__)

    def _record_trace_event(
        self,
        *,
        task_id: str,
        workflow_id: UUID,
        trace_id: str,
        event_type: str,
        outcome: str,
        step_id: str | None = None,
        attempt_id: str | None = None,
        attempt_number: int | None = None,
        tool_name: str | None = None,
        reason_code: str | None = None,
    ) -> None:
        """Persist safe execution metadata without allowing telemetry to affect work."""
        metadata: dict[str, object] = {
            "trace_id": trace_id,
            "workflow_id": str(workflow_id),
            "status": outcome,
        }
        if step_id is not None:
            metadata["step_id"] = step_id
        if attempt_id is not None:
            metadata["attempt_id"] = attempt_id
        if attempt_number is not None:
            metadata["attempt_number"] = attempt_number
        if tool_name is not None:
            metadata["tool_name"] = tool_name
        if reason_code is not None:
            metadata["reason_code"] = reason_code[:160]
        try:
            AuditLogger(self.repository).record(
                event_type=event_type,
                outcome=outcome,
                subject_type="task",
                subject_id=task_id,
                actor_type="system",
                metadata=metadata,
            )
        except Exception:  # noqa: BLE001
            # Observability failure must never trigger a duplicate side effect.
            self._logger.warning(
                "workflow_trace_event_persist_failed trace_id=%s event_type=%s",
                trace_id,
                event_type,
            )

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

    @staticmethod
    def request_digest(request: AgentPlanRequest) -> str:
        """Return the version-stable digest shared by API and worker replay."""
        return AgentWorkflowRunner._digest(request.canonical_payload())

    @staticmethod
    def build_durable_step_metadata(
        core: AgentCore,
        request: AgentPlanRequest,
        plan: dict[str, object],
    ) -> tuple[list[dict[str, object]], dict[int, object]]:
        """Build durable checkpoints and tool lookups in validated DAG order."""
        ordered_tools = core.ordered_tool_steps(request, plan)
        if len(ordered_tools) != len(request.tools):
            raise ValueError("Validated workflow graph does not cover every requested tool")

        definitions = {
            step.step_id: step
            for step in request.workflow_steps()
        }
        step_specs: list[dict[str, object]] = [
            {
                "step_number": 1,
                "step_key": "step-1",
                "depends_on": [],
                "kind": "provider_selection",
                "name": "provider_selection",
                "input_digest": None,
            }
        ]
        tools_by_execution_step: dict[int, object] = {}
        for runtime_step_number, request_step_number, requested_tool in ordered_tools:
            definition = core.tool_registry.get(requested_tool.name)
            step_specs.append(
                {
                    "step_number": runtime_step_number,
                    "step_key": request.tool_step_id(request_step_number, requested_tool),
                    "depends_on": list(
                        definitions[
                            request.tool_step_id(request_step_number, requested_tool)
                        ].depends_on
                    ),
                    "kind": (
                        "external_tool"
                        if definition.external_side_effect
                        else "safe_tool"
                    ),
                    "name": requested_tool.name,
                    "input_digest": core.workflow_step_input_digest(
                        request_step_number,
                        requested_tool,
                        step_id=request.tool_step_id(request_step_number, requested_tool),
                    ),
                }
            )
            tools_by_execution_step[runtime_step_number] = definition
        return step_specs, tools_by_execution_step

    def _durable_step_metadata(
        self,
        request: AgentPlanRequest,
        plan: dict[str, object],
    ) -> tuple[list[dict[str, object]], dict[int, object]]:
        return self.build_durable_step_metadata(self.core, request, plan)

    def _evaluate_workflow_tools(
        self,
        workflow_id: UUID,
        request: AgentPlanRequest,
        plan: dict[str, object],
        owner_user_id: str,
    ) -> dict[str, object] | None:
        """Evaluate persisted tool outcomes in the same order used by DAG execution."""
        ordered_tools = self.core.ordered_tool_steps(request, plan)
        if not ordered_tools:
            return None
        workflow = self.recovery.get_run(
            workflow_id, owner_user_id=owner_user_id
        )
        legacy_definition = int((workflow or {}).get("definition_version", 1)) < 3
        stored_steps = {
            str(
                step.get("step_key")
                or f"step-{step['step_number']}"
            ): step
            for step in (workflow or {}).get("steps", [])
        }
        criteria = []
        for runtime_number, request_number, requested_tool in ordered_tools:
            step_key = (
                f"step-{runtime_number}"
                if legacy_definition
                else request.tool_step_id(request_number, requested_tool)
            )
            step = stored_steps.get(step_key, {})
            status = step.get("status")
            if status == "succeeded":
                outcome = CriterionStatus.PASSED
                evidence_digest = step.get("output_digest")
            elif status == "failed":
                outcome = CriterionStatus.FAILED
                # Bind the digest to this persisted failure checkpoint rather than
                # hashing only the error code, which would collide across workflows.
                evidence_digest = self._digest(
                    {
                        "workflow_id": str(workflow_id),
                        "step_id": step_key,
                        "status": status,
                        "error_code": step.get("error_code") or "tool_execution_failed",
                        "attempt_count": step.get("attempt_count"),
                        "started_at": step.get("started_at"),
                        "finished_at": step.get("finished_at"),
                    }
                )
            else:
                # Includes unknown_outcome, retry_wait, pending and running.
                # An ambiguous or unfinished action must never be called passed.
                outcome = CriterionStatus.UNKNOWN
                evidence_digest = None
            criteria.append(
                EvaluationCriterion(
                    criterion_id=(
                        f"tool-step-{runtime_number}"
                        if legacy_definition or requested_tool.step_id is None
                        else f"tool-step-{step_key}"
                    ),
                    description=f"Tool execution completed: {requested_tool.name}",
                    status=outcome,
                    evidence_digest=evidence_digest,
                )
            )
        report = evaluate_criteria(criteria)
        return {
            **report.as_dict(),
            "correction_plan": build_correction_plan(report),
        }

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
        if not plan.get("execution_ready"):
            raise ValueError("Workflow plan is not executable")
        raw_steps = plan.get("steps", [])
        if not isinstance(raw_steps, list) or not raw_steps:
            raise ValueError("Workflow plan contains no executable steps")
        step_specs, tools_by_execution_step = self._durable_step_metadata(
            request, plan
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
                definition_version=3,
                owner_user_id=owner_user_id,
            )
            AuditLogger(self.repository).record(
                event_type="task.submitted",
                outcome="queued",
                subject_id=str(task.task_id),
                actor_type="user",
                actor_id=owner_user_id,
                metadata={
                    "task_type": task.task_type,
                    "risk_class": task.risk_class.value,
                    "decision": "allow",
                    "trace_id": str(task.task_id),
                    "workflow_id": str(workflow_id),
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
        trace_id = str(task.task_id)
        attempts: dict[int, StepAttempt] = {}
        runtime_step_ids = {
            runtime_number: request.tool_step_id(request_number, requested_tool)
            for runtime_number, request_number, requested_tool in self.core.ordered_tool_steps(
                request, plan
            )
        }

        try:
            self._record_execution_start(
                lease, increment_attempt=not worker_owned_lease
            )
            self.recovery.start_run(workflow_id, lease=lease)
            self._record_trace_event(
                task_id=str(task.task_id),
                workflow_id=workflow_id,
                trace_id=trace_id,
                event_type="agent.workflow.started",
                outcome="running",
            )
            provider_attempt = self.recovery.start_step(workflow_id, "step-1", lease=lease)
            self._record_trace_event(
                task_id=str(task.task_id),
                workflow_id=workflow_id,
                trace_id=trace_id,
                event_type="agent.workflow.step.started",
                outcome="running",
                step_id="step-1",
                attempt_id=provider_attempt.attempt_id,
                attempt_number=provider_attempt.attempt_number,
                tool_name="provider_selection",
            )
            provider_digest = self._digest(plan.get("selected_provider", {}))
            self.recovery.complete_step(
                workflow_id, provider_attempt, provider_digest, lease=lease
            )
            self._record_trace_event(
                task_id=str(task.task_id),
                workflow_id=workflow_id,
                trace_id=trace_id,
                event_type="agent.workflow.step.succeeded",
                outcome="succeeded",
                step_id="step-1",
                attempt_id=provider_attempt.attempt_id,
                attempt_number=provider_attempt.attempt_number,
                tool_name="provider_selection",
            )

            def on_step(number: int, status: str, error_code: str | None) -> None:
                if lease_lost.is_set():
                    raise RuntimeError("Workflow worker lease was lost")
                if status == "running":
                    step_key = runtime_step_ids[number]
                    attempts[number] = self.recovery.start_step(
                        workflow_id, step_key, lease=lease
                    )
                    definition = tools_by_execution_step.get(number)
                    self._record_trace_event(
                        task_id=str(task.task_id),
                        workflow_id=workflow_id,
                        trace_id=trace_id,
                        event_type="agent.workflow.step.started",
                        outcome="running",
                        step_id=step_key,
                        attempt_id=attempts[number].attempt_id,
                        attempt_number=attempts[number].attempt_number,
                        tool_name=getattr(definition, "name", "unknown"),
                    )
                elif status == "failed":
                    attempt = attempts.get(number)
                    if attempt is not None:
                        definition = tools_by_execution_step.get(number)
                        if definition is None:
                            raise RuntimeError("Failed workflow step has no DAG tool mapping")
                        failure_code = error_code or "tool_execution_failed"
                        self.recovery.fail_step(
                            workflow_id,
                            attempt,
                            failure_code,
                            unknown_outcome=definition.external_side_effect,
                            lease=lease,
                        )
                        self._record_trace_event(
                            task_id=str(task.task_id),
                            workflow_id=workflow_id,
                            trace_id=trace_id,
                            event_type=(
                                "agent.workflow.step.unknown_outcome"
                                if definition.external_side_effect
                                else "agent.workflow.step.failed"
                            ),
                            outcome=(
                                "unknown_outcome"
                                if definition.external_side_effect
                                else "failed"
                            ),
                            step_id=attempt.step_id,
                            attempt_id=attempt.attempt_id,
                            attempt_number=attempt.attempt_number,
                            tool_name=definition.name,
                            reason_code=failure_code,
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
                self._record_trace_event(
                    task_id=str(task.task_id),
                    workflow_id=workflow_id,
                    trace_id=trace_id,
                    event_type="agent.workflow.step.succeeded",
                    outcome="succeeded",
                    step_id=attempt.step_id,
                    attempt_id=attempt.attempt_id,
                    attempt_number=attempt.attempt_number,
                    tool_name=getattr(tools_by_execution_step.get(number), "name", "unknown"),
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
            evaluation = self._evaluate_workflow_tools(
                workflow_id, request, plan, owner_user_id
            )
            execution = {
                **execution,
                "evaluation": evaluation,
                "evaluation_scope": "tool_execution_only" if request.tools else None,
            }
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
                self._record_trace_event(
                    task_id=str(task.task_id),
                    workflow_id=workflow_id,
                    trace_id=trace_id,
                    event_type="agent.workflow.cancelled",
                    outcome="cancelled",
                    reason_code="owner_cancellation",
                )
                return {
                    "workflow_id": str(workflow_id),
                    "execution": execution,
                }
            if execution["execution_completed"]:
                self.recovery.finish_run(workflow_id, "succeeded", lease=lease)
                self.jobs.transition(task.task_id, TaskStatus.SUCCEEDED, lease=lease)
                self._record_trace_event(
                    task_id=str(task.task_id),
                    workflow_id=workflow_id,
                    trace_id=trace_id,
                    event_type="agent.workflow.succeeded",
                    outcome="succeeded",
                )
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
                self._record_trace_event(
                    task_id=str(task.task_id),
                    workflow_id=workflow_id,
                    trace_id=trace_id,
                    event_type=(
                        "agent.workflow.recovery_required"
                        if target is TaskStatus.WAITING_APPROVAL
                        else "agent.workflow.failed"
                    ),
                    outcome=(
                        "recovery_required"
                        if target is TaskStatus.WAITING_APPROVAL
                        else "failed"
                    ),
                    reason_code=execution.get("error_code")
                    if isinstance(execution.get("error_code"), str)
                    else None,
                )
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
                self._record_trace_event(
                    task_id=str(task.task_id),
                    workflow_id=workflow_id,
                    trace_id=trace_id,
                    event_type="agent.workflow.interrupted",
                    outcome="interrupted",
                    reason_code="execution_exception",
                )
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
                "evaluation": execution.get("evaluation"),
                "evaluation_scope": execution.get("evaluation_scope"),
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
        definition_version = int(workflow["definition_version"])
        decision = self.recovery.resume_decision(
            workflow_id,
            request_digest,
            definition_version=definition_version,
            owner_user_id=owner_user_id,
        )
        if decision.decision == "resume" and definition_version >= 3:
            identity_matches = any(
                int(step["step_number"]) == decision.next_step
                and str(step["step_key"]) == decision.next_step_id
                for step in workflow["steps"]
            )
            if not decision.next_step_id or not identity_matches:
                raise ValueError(
                    "Workflow resume decision has no consistent stable step identity"
                )
        if decision.decision not in {"resume", "finish"} or (
            decision.decision == "resume" and decision.next_step is None
        ):
            raise ValueError(f"Workflow is not resumable: {decision.decision}")

        raw_steps = plan.get("steps", [])
        if not plan.get("execution_ready") or not isinstance(raw_steps, list):
            raise ValueError("Current request is not executable")
        expected_specs, _tools_by_execution_step = self._durable_step_metadata(
            request, plan
        )
        if definition_version < 3:
            # Historical workflows did not persist caller-defined IDs or DAG edges.
            # Keep their exact numeric contract; never infer a reordered legacy plan.
            expected = [
                (
                    int(step["step_number"]),
                    str(step["kind"]),
                    str(step["name"]),
                    step.get("input_digest"),
                )
                for step in expected_specs
            ]
            stored = [
                (
                    int(step["step_number"]),
                    step["step_kind"],
                    step["step_name"],
                    step.get("input_digest"),
                )
                for step in workflow["steps"]
            ]
            if len(expected) != len(stored) or any(
                expected_step[:3] != stored_step[:3]
                or (
                    expected_step[3] != stored_step[3]
                    and not (definition_version < 2 and stored_step[3] is None)
                )
                for expected_step, stored_step in zip(expected, stored, strict=True)
            ):
                raise ValueError("Current workflow plan differs from the stored legacy definition")
        else:
            expected_by_id = {
                str(step["step_key"]): step for step in expected_specs
            }
            stored_by_id = {
                str(step["step_key"]): step for step in workflow["steps"]
            }
            if set(expected_by_id) != set(stored_by_id):
                raise ValueError("Current workflow step identities differ from the stored definition")
            for step_key, expected_step in expected_by_id.items():
                stored_step = stored_by_id[step_key]
                if (
                    expected_step["kind"] != stored_step["step_kind"]
                    or expected_step["name"] != stored_step["step_name"]
                    or expected_step.get("input_digest") != stored_step.get("input_digest")
                    or sorted(expected_step.get("depends_on", []))
                    != sorted(stored_step.get("depends_on", []))
                ):
                    raise ValueError(
                        f"Current workflow definition changed for step identity: {step_key}"
                    )

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
            definition_version=int(_workflow["definition_version"]),
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
        _step_specs, tools_by_execution_step = self._durable_step_metadata(
            request, plan
        )
        legacy_definition = int(_workflow["definition_version"]) < 3
        runtime_step_ids = {
            runtime_number: (
                f"step-{runtime_number}"
                if legacy_definition
                else request.tool_step_id(request_number, requested_tool)
            )
            for runtime_number, request_number, requested_tool in self.core.ordered_tool_steps(
                request, plan
            )
        }
        succeeded_step_ids = {
            str(step["step_key"])
            for step in _workflow["steps"]
            if step["status"] == "succeeded"
        }
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
                provider_step = next(
                    (step for step in _workflow["steps"] if step["step_key"] == "step-1"),
                    None,
                )
                if provider_step is None:
                    raise RuntimeError("Workflow provider-selection identity is missing")
                if provider_step["status"] != "succeeded":
                    provider_attempt = self.recovery.start_step(
                        workflow_id, "step-1", lease=lease
                    )
                    self.recovery.complete_step(
                        workflow_id,
                        provider_attempt,
                        self._digest(plan.get("selected_provider", {})),
                        lease=lease,
                    )
                    succeeded_step_ids.add("step-1")

                def on_step(
                    number: int, status: str, error_code: str | None
                ) -> None:
                    if lease_lost.is_set():
                        raise RuntimeError("Workflow worker lease was lost")
                    if status == "running":
                        step_key = runtime_step_ids[number]
                        attempts[number] = self.recovery.start_step(
                            workflow_id,
                            number if legacy_definition else step_key,
                            lease=lease,
                        )
                    elif status == "failed":
                        attempt = attempts.get(number)
                        if attempt is not None:
                            definition = tools_by_execution_step.get(number)
                            if definition is None:
                                raise RuntimeError("Failed workflow step has no DAG tool mapping")
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
                    start_step=(
                        max(2, int(decision.next_step or 2))
                        if legacy_definition else 2
                    ),
                    skip_step_ids=(
                        None if legacy_definition else succeeded_step_ids
                    ),
                    should_cancel=should_cancel,
                )

            evaluation = self._evaluate_workflow_tools(
                workflow_id, request, plan, owner_user_id
            )
            execution = {
                **execution,
                "evaluation": evaluation,
                "evaluation_scope": "tool_execution_only" if request.tools else None,
            }
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
                "evaluation": execution.get("evaluation"),
                "evaluation_scope": execution.get("evaluation_scope"),
            },
        }
