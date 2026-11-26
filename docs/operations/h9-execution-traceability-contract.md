# H15 / X7 — Execution Traceability: implementation status

Status: **Hub-local task-bound traceability is implemented and covered by tests. Cross-project distributed trace correlation remains partial.**

Historical note: This document was previously titled H9 under an older phase map. The current 73-phase roadmap assigns observability to **H15** and shared observability contracts to **X7**. Older phase labels do not redefine the current roadmap.

## Verified implementation on Hub main

The Hub has a server-generated, owner-scoped execution trace for one task and its task-linked workflow:

- Task submission creates the task UUID on the server and returns it as X-Trace-ID. An idempotent replay returns the same task/trace identity.
- The current trace identity is intentionally the task UUID: trace_id == task_id. It is not a separate top-level operation UUID.
- AgentWorkflowRunner carries that trace identity through workflow lifecycle events, provider/step attempts, registered tool lifecycle events, resume, interruption, and terminal outcomes.
- Trace event metadata is allow-listed and bounded. Verified fields include task/trace identity, workflow ID, step ID, attempt ID/number, registered tool name, status, and bounded reason code. Raw prompts, tool inputs/outputs, credentials, and arbitrary provider payloads are not part of the trace contract.
- GET /agent/traces/{trace_id} checks ownership server-side and returns a bounded, cursor-paginated task-linked event timeline. Request IDs remain distinct from execution trace IDs.
- The operator workflow dashboard exposes a read-only Timeline view and paginates events.
- Trace persistence is written through the existing audit-event storage. Observability failure is handled separately from workflow execution and must not cause a completed side effect to be replayed.

## Source and test evidence

The implementation is covered by tests/test_agent_traceability.py, including:

- server-generated trace identity and the X-Trace-ID response header;
- owner isolation for trace reads;
- allow-listed workflow/step/attempt/tool metadata;
- cursor pagination and timestamp normalization;
- the dashboard Timeline and safe DOM rendering;
- suppressing trace lookup when a workflow has no valid task ID.

Relevant implementation paths:

- backend/mrhub/api/routes/tasks.py
- backend/mrhub/api/routes/agent.py
- backend/mrhub/agents/workflow_runner.py
- backend/mrhub/infrastructure/database.py
- backend/mrhub/security/audit.py
- backend/mrhub/web/app.js
- backend/mrhub/web/app.css

This section records source/test evidence, not production deployment or fleet-wide acceptance.

## Current identity and correlation contract

- trace_id: server-generated task UUID; immutable for that task and stable across idempotent replay.
- task_id: the same UUID as trace_id in the current Hub implementation.
- workflow_id: durable workflow entity ID linked to the task.
- step_id: stable workflow step identifier.
- attempt_id: unique execution attempt identifier; retry attempts retain distinct attempt identities.
- request_id: identifies one HTTP request and is distinct from trace_id.
- correlation_id: diagnostic metadata for cross-service/request correlation; it is not an authentication, authorization, ownership, or idempotency credential.

Do not describe the current Hub trace as an independent request-level UUID with a parent-event graph. The current verified scope is one task and its task-linked workflow.

## Remaining H15 / X7 work

1. Define and test a versioned cross-project correlation contract that joins the EL_AI Bridge job, Hub task, Hub workflow, and Telegram delivery lifecycle without conflating entity IDs.
2. Decide whether a separate top-level operation ID is required for workflows that create multiple tasks or span services. Preserve the current task UUID semantics for v1 compatibility.
3. Propagate and validate correlation metadata at each service boundary; prove concurrent task isolation and cleanup on success, exception, timeout, and cancellation.
4. Add owner-scoped cross-service lookup only after the identity mapping and authorization model are explicit.
5. Extend metrics beyond process-local snapshots where deployment architecture supports it; add bounded retention, export, alerting, and operational runbooks as separate release-gated changes.
6. Capture live-service and deployment evidence separately from unit tests and GitHub Actions.

## Boundaries

- A correlation ID is diagnostic metadata, never a capability or permission grant.
- Trace queries must remain owner-scoped, bounded, and paginated.
- Telemetry must not contain raw prompts, message bodies, secrets, credentials, file contents, or arbitrary tool payloads by default.
- Do not infer successful delivery, production deployment, fleet-wide observability, or live Telegram/Cloudflare acceptance from source tests.
- This document does not authorize production migration, external telemetry spend, or service provisioning.

## Rollback

This is an implementation-status and contract-document correction only. Reverting the document restores the earlier proposal text and does not change runtime behavior, database schema, or deployed services.
