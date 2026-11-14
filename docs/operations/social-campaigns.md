# Cross-platform social campaigns

The campaign API links one approved Instagram Reel draft to one approved Telegram lesson draft. It reuses the existing content-draft repository, durable publish schedules, and worker dispatcher.

## Lifecycle

1. Create the Instagram draft with `content_type=reel` and an owner-owned MP4 asset that has passed the `video_render_cut_v1` processing profile.
2. Create the Telegram companion lesson as a Telegram draft.
3. Approve both drafts. Editing either draft revokes its approval through the existing draft lifecycle.
4. Create a campaign by supplying the two draft IDs.
5. Schedule the campaign once. Both platform schedules are inserted in one SQLite transaction with a shared scheduled time and independent idempotency keys.
6. The existing worker dispatches each schedule through its configured provider adapter. Campaign status is derived from both schedule outcomes; it does not claim cross-provider atomic delivery.
7. A campaign can be cancelled only while both schedules are still pending. Once either delivery starts, paired cancellation is rejected.

## API

All endpoints require the existing authenticated user session.

- `GET /content/campaigns?limit=50`
- `POST /content/campaigns`
- `GET /content/campaigns/{campaign_id}`
- `POST /content/campaigns/{campaign_id}/schedule`
- `POST /content/campaigns/{campaign_id}/cancel`

Create payload:

```json
{
  "title": "Account security mini-campaign",
  "instagram_draft_id": "UUID",
  "telegram_draft_id": "UUID"
}
```

Schedule payload:

```json
{
  "scheduled_at": "2026-12-01T17:00:00+00:00"
}
```

Campaign status values: `draft`, `scheduled`, `published`, `partial`, `failed`, `cancelled`, `unknown_outcome`.

A campaign is considered published only when both platform schedules report `published`. If one publishes while the other fails, is cancelled, or becomes ambiguous, the campaign reports `partial`. If any delivery is ambiguous and none has completed, the campaign reports `unknown_outcome`. Provider delivery is not exactly-once; `unknown_outcome` must be reconciled rather than blindly retried.

## Optional Follow/Share CTA before resource delivery

The comment-to-resource reply may invite the recipient to follow the page and share the post before showing the educational resource. These are voluntary support requests, not access conditions.

Required behavior:
- Put the Follow and Share invitation before the resource link.
- Include the resource URL in the same reply, immediately after the invitation.
- Send the resource whether the recipient follows, does not follow, shares, or does not share.
- Never query follower/share state, branch on those states, or claim either action was verified.
- Use respectful language; do not imply that access, eligibility, or delivery depends on engagement.

The backend helper `mrhub.content.resource_reply.build_optional_support_resource_reply` composes this copy and rejects non-HTTPS or malformed resource URLs. It intentionally has no Follow/Share state parameters. This helper is not a PostZen transport and does not send messages.

## External activation checklist

- Verify the Instagram professional account, current Graph API version, scopes, public HTTPS media origin, and real-account Reel acceptance.
- Rotate any Telegram bot token that may have appeared in diagnostic URLs. Store the replacement only in the deployment secret store and confirm the target channel ID.
- PostZen comment automation inventory was empty at the last review. Keep automation inactive until the exact per-post keyword, final user-approved DM copy, public educational resource URL, target account, and scopes are confirmed.
- The selected resource URL must be a real public HTTPS destination; do not activate a placeholder or assume the Telegram channel URL is the intended resource.
- Use only supported per-post comment-triggered private replies; respect provider deduplication, send limits, and platform messaging windows. Do not send unsolicited bulk DMs.
- Record real-provider post IDs and provider analytics separately from mocked CI. Missing provider metrics must be labelled unavailable, not estimated.
- Do not enable unattended publishing until CI is green, credentials and scopes are verified, and one controlled test campaign has explicit approval.
