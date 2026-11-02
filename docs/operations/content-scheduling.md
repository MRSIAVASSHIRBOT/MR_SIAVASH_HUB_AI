# Durable content scheduling (v1)

This increment adds an authenticated, owner-scoped schedule record for approved Instagram and Telegram drafts.

## API

- `POST /content/drafts/{draft_id}/schedule` with `{"scheduled_at":"<timezone-aware ISO-8601 timestamp>"}`
- `GET /content/schedules?status=scheduled&limit=50`
- `POST /content/schedules/{schedule_id}/cancel`

Only approved drafts can be scheduled, the scheduled time must be in the future, and generic drafts are rejected. A draft can have only one active schedule. Schedule rows capture the approved draft version and content hash so later delivery can detect stale approvals. Records are owner-scoped and audit events contain reason codes and IDs, not post bodies.

## Important runtime boundary

**This version persists and manages schedules; it does not yet publish posts automatically.** The Worker is pull-driven and no external publishing adapter is registered by this change. Do not interpret `status=scheduled` as a successfully published post. The next increment should add a due-schedule dispatcher with lease/claim semantics, verify that the current draft is still approved and matches the captured version/hash, and call an explicitly configured provider adapter. Unknown external outcomes must not be retried blindly because that could duplicate a post.

## Delivery states reserved in the schema

- `scheduled`: waiting for a due-schedule dispatcher.
- `publishing`: claimed for a delivery attempt.
- `published`: provider confirmed success.
- `failed`: known failure.
- `unknown_outcome`: the provider may have accepted the post, but confirmation was lost; requires reconciliation before retry.
- `cancelled`: cancelled before a delivery claim.

The schema is forward-only through migration 14. Do not edit released migration definitions; future changes require a new migration.
