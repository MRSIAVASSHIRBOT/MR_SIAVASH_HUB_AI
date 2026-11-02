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

Draft management is separate from publishing. Scheduled publishing uses an explicit pull-driven dispatcher, opt-in provider adapters, approval/version/hash revalidation, bounded retry for known transient failures, and an `unknown_outcome` state for ambiguous provider results. It does not run automatically at API startup. Local media upload and bounded FFmpeg processing are implemented separately. Draft storage does not guarantee erasure of old database backup copies.


## Media attachments

A Telegram draft may reference an owner-owned JPEG, PNG, or MP4 asset via `media_asset_id`. An Instagram draft may reference an owner-owned JPEG or PNG asset; video publishing is not implemented by the Instagram adapter. The asset ID is included in the content hash and each version snapshot. Attaching, replacing, or detaching media creates a new draft version and revokes approval. Deleting an asset that is referenced by a current or historical draft version is rejected; delete the draft/history first if the media should be removed permanently.

Instagram schedules require the opt-in signed public-media route because Meta must fetch a public HTTPS image URL. That route is disabled until `MRH_PUBLIC_MEDIA_BASE_URL` and `MRH_PUBLIC_MEDIA_SIGNING_KEY` are configured. External reachability, edge rate limiting, Graph API credentials/scopes, and a controlled real-account acceptance test remain deployment requirements.
