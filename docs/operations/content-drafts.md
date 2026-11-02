# Local Content Draft Lifecycle

The initial content vertical stores private drafts and revisions. It does not publish to Instagram, Telegram, or any other external service.

## Endpoints

All routes require the authenticated owner.

- `POST /content/drafts` — create a draft for `instagram`, `telegram`, or `generic`, with a content type, title, body, and hashtags.
- `GET /content/drafts?limit=50&status=draft` — list owned drafts. Status can be `draft`, `approved`, or `archived`.
- `GET /content/drafts/{draft_id}` — read an owned draft.
- `PATCH /content/drafts/{draft_id}` — edit content. Each successful edit increments the revision and automatically resets approval to `draft`.
- `GET /content/drafts/{draft_id}/versions` — read owner-scoped revision history.
- `POST /content/drafts/{draft_id}/approve` — explicitly approve the current revision.
- `POST /content/drafts/{draft_id}/revoke-approval` — revoke a prior approval.
- `POST /content/drafts/{draft_id}/archive` and `POST /content/drafts/{draft_id}/restore` — archive or restore a draft.
- `DELETE /content/drafts/{draft_id}` — permanently delete the draft and its revisions.

## Deduplication and approval

- A SHA-256 content fingerprint is computed from platform, content type, normalized body, and normalized hashtags. The same owner cannot create or update a draft to duplicate an existing draft with the same fingerprint.
- A duplicate create/update returns HTTP 409. No content is overwritten silently.
- Approval is an explicit state transition tied to the authenticated owner. Any content edit revokes approval and creates a new revision.
- Audit records contain operation identifiers and reason codes, not draft text.
- `approved` means the owner approved a stored draft. It does not authorize or trigger external publishing.

## Current limits

This milestone is draft management only. There is no social publishing endpoint, no external scheduler, no media upload, and no FFmpeg process invocation. Those require separate provider/asset adapters, sandboxing, approval binding, and integration tests. Draft storage does not guarantee erasure of old database backup copies.
