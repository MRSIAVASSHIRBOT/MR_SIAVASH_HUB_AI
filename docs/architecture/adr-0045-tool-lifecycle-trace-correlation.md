# ADR-0045 — Correlate tool lifecycle events with workflow attempts

- Status: Accepted
- Date: 2026-11-25
- Scope: H6 Execution Engine and H9 Observability

## Context

The tool registry emits metadata-only lifecycle stages for input validation, authorization,
handler execution, output validation, and completion. The workflow runner already records
task/workflow/step/attempt identifiers for durable workflow transitions, but it did not
forward those identifiers to the tool lifecycle observer in either fresh execution or
resume. This left tool-level events outside the task's correlated audit timeline.

## Decision

The workflow runner supplies an observer to both normal and resumed calls to
`AgentCore.execute`. Each lifecycle event is persisted through the existing
`AuditLogger` as `agent.workflow.tool.<stage>`, with the stage as its outcome and the
active task, workflow, step, attempt, and registered tool identifiers in allow-listed
metadata. Reason codes remain bounded by the existing audit sanitizer.

The observer deliberately does not persist input/output digests, prompts, raw tool
payloads, tool results, exception text, credentials, or arbitrary provider data.
Audit persistence remains best-effort and must never alter tool execution or replay
behavior. If an event arrives without an active durable attempt, the runner emits a
sanitized warning and drops the uncorrelated event rather than creating misleading
trace data.

## Consequences

- Tool lifecycle stages can be correlated with the existing workflow and task timeline.
- The same contract applies when a workflow resumes after interruption.
- No schema migration, new dependency, endpoint, or live-service change is required.
- The cross-process runtime smoke test verifies correlation identifiers and the
  absence of raw input/output fields.
