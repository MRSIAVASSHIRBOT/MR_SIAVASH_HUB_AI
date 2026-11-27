# H10 — Task Lifecycle Engine

Status: PARTIAL. This document follows the v6 ecosystem roadmap, where H10 owns Task Identity, State Transitions, Priority, Deadlines, Cancellation and Task History.

## Existing lifecycle foundation

The current Hub implementation already provides:

- Immutable \`TaskRecord\` values with UUID task identity, task type, risk class, creation/update timestamps and description.
- A closed \`TaskStatus\` enum: queued, running, waiting_approval, succeeded, failed, cancelled and rejected.
- A deterministic transition matrix in \`JobEngine\`; terminal states cannot transition further.
- Compare-and-set state updates in \`TaskRepository.update_status\`, with optional worker lease owner, expiry and fencing-token checks.
- Cancellation for queued or waiting-approval tasks only. Running tasks cannot be cancelled through the pending-cancel operation.
- Task lifecycle audit events and bounded/keyset-paginated history for paired Telegram clients.

## This implementation slice

The \`feat/h10-task-lifecycle-owner-scope-20261127\` branch adds the following to the authenticated owner API:

- Task detail reads are filtered to the exact authenticated user who submitted the task.
- Task-result reads enforce the same owner check before retrieving the result.
- Task lists contain only tasks whose \`task.submitted\` audit event identifies the authenticated user.
- \`POST /tasks/{task_id}/cancel\` cancels an owned task only while it is queued or waiting for approval. A concurrent state change or an already-started/terminal task returns HTTP 409.
- \`GET /tasks/{task_id}/events\` exposes bounded, stable keyset pagination over sanitized lifecycle events. The cursor is opaque and validated; each page independently checks task ownership.
- Unknown, foreign or non-owned task IDs return the same HTTP 404 response to avoid disclosing whether another user's task exists.

Ownership for this compatibility slice is derived from the task's \`task.submitted\` audit event (\`actor_type=user\`, \`actor_id=owner_user_id\`). No owner is inferred for legacy or internally-created tasks without that ownership event; those tasks remain hidden from the user-facing owner API.

## Explicitly not complete

The v6 H10 phase is not complete because the current \`TaskRecord\` and \`tasks\` table still do not define first-class priority or deadline fields. In particular:

- No persisted priority level or priority scheduling policy exists.
- No \`deadline_at\`/SLA field, overdue state, expiry policy or deadline-triggered event exists.
- Task ownership is inferred from the submission audit event in this slice; a future additive schema migration should put owner identity directly on the task record and define migration/backfill policy for older rows.
- No complete owner-facing API for rescheduling, reprioritization or deadline changes is added.
- Cancellation remains a request for queued/approval-waiting tasks only; cooperative cancellation of running workers is a separate execution/recovery concern.
- The complete event-retention, export and administrative history policy remains part of operational acceptance.

## Verification

The feature branch adds API coverage for owner isolation across list/detail/result/history/cancel routes, queued-task cancellation, rejection of repeated cancellation, and cursor pagination/malformed-cursor handling. The existing test for dashboard filtering is updated to attach an owner submission event to its fixture.

Hosted exact-head GitHub Actions are the source of truth for test status. Until those checks complete successfully, this change is not accepted. No production deployment, data migration, running-worker cancellation or live service acceptance is claimed.
