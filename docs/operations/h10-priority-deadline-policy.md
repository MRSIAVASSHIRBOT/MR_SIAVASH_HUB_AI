# H10 — Task Priority and Deadline Policy

Status: implementation slice under review. This document follows the v6 H10 Task Lifecycle Engine scope.

## Data contract

Each Task now carries:

- \`priority\`: \`low\`, \`normal\`, \`high\`, or \`urgent\`. The default is \`normal\`.
- \`deadline_at\`: optional timezone-aware timestamp. Naive timestamps are rejected; persisted values are normalized to UTC.
- Existing task identity, risk class, status, created/updated timestamps and description remain unchanged.

Migration 60 adds the \`priority\` and \`deadline_at\` columns and a dispatch-oriented index. Existing rows retain their data and receive the safe defaults \`normal\` and NULL. Earlier migration definitions are not modified.

## Scheduling order

The pull-driven worker selects eligible queued tasks using this order:

1. Effective priority, descending. Base ranks are low=0, normal=1, high=2, urgent=3.
2. Aging: one effective priority level is added for each full hour in the queue, capped at urgent. This prevents a steady stream of new urgent tasks from starving older lower-priority tasks indefinitely.
3. Deadline, ascending, with tasks that have a deadline ahead of tasks without one when effective priority is equal.
4. Creation time and task ID for deterministic FIFO tie-breaking.

This is scheduling precedence, not a policy override. A task in \`waiting_approval\` is not eligible for the worker queue, and a priority label does not grant tool permissions, waive review, or alter the risk class.

## Approval and idempotency compatibility

For an existing task with default priority and no deadline, the legacy action fingerprint shape is preserved. For non-default scheduling metadata, priority and/or deadline are included in the fingerprint so an approval cannot be reused for a task with changed scheduling parameters.

Likewise, the existing idempotency digest format is preserved for requests with default priority and no deadline. Non-default priority or a deadline is included in the canonical request digest, so reusing a key with different scheduling data returns a conflict.

## Boundaries and remaining H10 work

This slice stores and schedules priority/deadline metadata; it does not yet implement:
- A separate persisted overdue status or automatic overdue notifications.
- A full SLA/escalation policy or deadline-triggered cancellation.
- User-facing priority/deadline editing after task creation.
- A configurable aging interval or tenant-specific scheduling fairness.
- A full owner-ID schema migration for historical task records.

Deadlines do not implicitly cancel work, and overdue tasks remain in their current lifecycle status. Existing policy and approval gates remain authoritative.

## Verification

The PR adds migration compatibility coverage, API and Telegram idempotency tests, timezone validation/normalization tests, scheduler ordering tests and priority-aging tests. Hosted exact-head Actions are required before merge. No production database migration or deployment is performed by this PR.
