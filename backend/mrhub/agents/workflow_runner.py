"""Synchronous request-scoped workflow runner backed by durable Job state."""

from __future__ import annotations

import hashlib
import json
from mrhub.agents.core import AgentCore, AgentPlanRequest
from mrhub.domain.tasks import TaskRecord, TaskStatus
from mrhub.infrastructure.database import TaskRepository
from mrhub.jobs.engine import JobEngine
from mrhub.jobs.recovery import StepAttempt, WorkflowRecoveryRepository
from mrhub.security.audit import AuditLogger


class AgentWorkflowRunner:
    """Run supplied inputs in memory while persisting only lifecycle and digests."""

    def __init__(self, repository: TaskRepository, core: AgentCore) -> None:
        self.repository = repository
        self.core = core
        self.jobs = JobEngine(repository)
        self.recovery = WorkflowRecoveryRepository(repository.database_path)

    @staticmethod
    def _digest(value: object) -> str:
        encoded = json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
        return hashlib.sha256(encoded).hexdigest()

    def execute(
        self,
        request: AgentPlanRequest,
        plan: dict[str, object],
        request_digest: str,
    ) -> dict[str, object]:
        """Create a linked Job/Workflow, then execute each validated step in order."""
        raw_steps = plan.get("steps", [])
        if not isinstance(raw_steps, list) or not raw_steps:
            raise ValueError("Workflow plan contains no executable steps")
        step_specs = [
            {
                "step_number": int(step["step"]),
                "kind": str(step["kind"]),
                "name": str(step.get("name") or step["kind"]),
            }
            for step in raw_steps
            if isinstance(step, dict)
        ]
        task = TaskRecord(
            task_type="agent.workflow",
            description="Agent workflow execution",
        )
        workflow_id = self.recovery.create_run(
            request_digest,
            step_specs,
            task=task,
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
        self.recovery.start_run(workflow_id)
        attempts: dict[int, StepAttempt] = {}

        try:
            provider_attempt = self.recovery.start_step(workflow_id, 1)
            provider_digest = self._digest(plan.get("selected_provider", {}))
            self.recovery.complete_step(workflow_id, provider_attempt, provider_digest)

            def on_step(number: int, status: str, error_code: str | None) -> None:
                if status == "running":
                    attempts[number] = self.recovery.start_step(workflow_id, number)
                elif status == "failed":
                    attempt = attempts.get(number)
                    if attempt is not None:
                        self.recovery.fail_step(
                            workflow_id,
                            attempt,
                            error_code or "tool_execution_failed",
                            unknown_outcome=True,
                        )

            def on_step_result(number: int, output_digest: str) -> None:
                attempt = attempts.get(number)
                if attempt is None:
                    raise RuntimeError("Workflow step result has no active attempt")
                self.recovery.complete_step(workflow_id, attempt, output_digest)
                del attempts[number]

            execution = self.core.execute(
                request,
                on_step=on_step,
                on_step_result=on_step_result,
            )
        except Exception as exc:
            self.recovery.mark_interrupted(workflow_id)
            current = self.recovery.get_run(workflow_id)
            if current is not None and current["status"] == "running":
                self.recovery.finish_run(workflow_id, "failed")
            self.jobs.transition(task.task_id, TaskStatus.FAILED)
            raise RuntimeError("Workflow execution stopped; inspect its recovery state") from exc

        if execution["execution_completed"]:
            self.recovery.finish_run(workflow_id, "succeeded")
            self.jobs.transition(task.task_id, TaskStatus.SUCCEEDED)
        else:
            current = self.recovery.get_run(workflow_id)
            if current is not None and current["status"] == "running":
                self.recovery.finish_run(workflow_id, "failed")
            self.jobs.transition(task.task_id, TaskStatus.FAILED)

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
