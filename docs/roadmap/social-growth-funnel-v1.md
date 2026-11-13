# Social Growth Funnel v1 — Engineering Plan

Status: implementation in progress; campaign linkage is implemented on the feature branch, while CI and external account acceptance remain pending.
Base commit: b1c66a36074b8bb0df3ccd1d9658632925303dc5
Branch: feat/social-growth-funnel-v1

## Product outcome

Build a compliant, low-cost content funnel for MR_SIAVASH_IR_BOT:
1. Research and validate a useful topic.
2. Produce an educational short-form video and a substantive companion Telegram lesson.
3. Review and approve both assets as one campaign.
4. Publish Instagram Reels and Telegram content through supported APIs.
5. Optionally reply to eligible Instagram comments with a requested resource link using the connected PostZen account.
6. Measure reach, engagement, DM delivery, Telegram joins/clicks, and content quality.

No follow-gating, forced follows, unsolicited bulk DMs, scraping private data, or engagement manipulation. A comment-triggered private reply must comply with Meta's messaging rules and PostZen's documented limits. A user may access the promised educational resource without being forced to follow.

## Verified repository baseline (main, 2026-11-14)

- FastAPI/SQLite owner-scoped content drafts, revision history, deduplication, explicit approval/revocation, and audit events exist.
- Durable schedules capture approved revision/hash and support cancellation.
- ContentScheduleDispatcher is integrated with WorkerEngine; worker_service runs a pull loop. Dispatch is fail-closed when provider credentials are missing.
- Telegram Bot API adapter supports text and approved JPEG/PNG/MP4 assets.
- InstagramGraphImageAdapter supports only image containers (JPEG/PNG), not Reels/video.
- Instagram publishing requires a professional account, Graph API credentials, and a publicly reachable signed HTTPS media origin.
- Provider delivery is not exactly-once. Ambiguous outcomes enter unknown_outcome and must be reconciled before retry.
- Video intelligence/generation/render modules and FFmpeg processing exist; their output-to-social publishing handoff needs an integration audit.
- PostZen Default profile has connected Instagram and Telegram accounts. The comment-automation inventory is empty. The API key is valid. Do not activate any live comment/DM automation until copy, resource URL, scope, and behavior are explicitly approved.
- Current external account credentials, Meta scopes, public media reachability, and real-account publishing have not been verified by this repository audit.

## Current implementation status (feature branch)

- Instagram Reels adapter: implemented with bounded polling of the same container; only a confirmed FINISHED container is published.
- Signed public media: JPEG/PNG/MP4 path and owner-scoped processed-render checks are implemented.
- Reel draft type: database migration 36 rebuilds the draft/version/schedule tables to allow `reel` while preserving existing records.
- Cross-platform campaign linkage: migration 37, owner-scoped repository, authenticated API, atomic paired scheduling, paired cancellation, and API tests are implemented.
- Existing content scheduler and worker are reused; no parallel scheduler was added.
- CI for the current feature head is pending. Do not treat this branch as production-ready until every required check passes.
- PostZen Instagram comment automation inventory currently returns zero automations. Do not create or activate one until the exact keyword, approved DM copy, and public resource URL are supplied and reviewed.
- A previous Telegram diagnostic exposed a bot-token-bearing URL in stored error details. Rotate the bot token through BotFather and update the connected secret before enabling Telegram publishing. Do not copy tokens into chat or source control.

## Workstreams

### A. Reels publishing
- Extend the Instagram adapter with the official Graph API Reels container/publish flow.
- Extend signed public media delivery to approved MP4 assets, with strict MIME, size, signature-expiry, ownership, and content-hash checks.
- Verify Graph API version and current Meta requirements before implementation.
- Keep image publishing unchanged and preserve existing safety/error classifications.
- Add mocked unit tests for request shape, validation, transient rejection, permanent rejection, and ambiguous outcomes.
- Real account acceptance remains a separately approved manual test.

### B. Campaign orchestration
- Link one Instagram draft, one Telegram lesson, media assets, campaign metadata, and a shared campaign ID.
- Require both content items to be reviewed; edits revoke approval.
- Preserve idempotency, stale approval checks, emergency stop, audit records, and owner isolation.
- Avoid adding a second scheduler or duplicate content repository.

### C. Comment-to-resource DM
- Prefer the existing connected PostZen account and supported Comment Automation API; do not build unofficial Instagram automation.
- Use per-post keyword triggers and one useful resource link or short resource message.
- Confirm the account has required comment and messaging scopes before activation.
- Do not require a follow to receive the resource; no follow-gating.
- Respect one private reply per comment and platform time windows; deduplicate and cap sends.
- Create inactive/draft configuration first. Activation requires explicit review of the exact keywords, DM copy, destination URL, and account.

### D. Telegram education engine
- Reuse Telegram adapter and bot integration; distinguish the public channel publisher from the private Hub pairing bot.
- Publish substantive companion lessons, not just a link or teaser.
- Add campaign/source tracking to links without collecting unnecessary personal data.
- Keep Telegram daily text cadence within the account's existing quota.

### E. Analytics
- Capture provider post IDs, campaign IDs, timestamps, format, topic, and approved tracking parameters.
- Build a weekly report for views/reach, interactions, comments, DM sends/failures, link clicks, and Telegram growth where providers expose them.
- Clearly label unavailable metrics; never infer private Instagram insights from public data.

## Delivery sequence

1. Complete integration audit and verify current tests/configuration.
2. Implement and test MP4 signed-media delivery and Instagram Reels adapter.
3. Implement campaign linkage and cross-platform publishing acceptance tests. (feature-branch implementation completed; CI verification pending)
4. Configure one inactive PostZen comment automation for review only after keyword, DM copy, and resource URL are approved.
5. Run a controlled test with one harmless campaign after explicit approval.
6. Enable scheduled operation only after successful acceptance and quota checks.
7. Add weekly reporting and tune topics based on observed outcomes.

## Acceptance criteria

- Reels are published only from approved owner-owned MP4 assets over verified public HTTPS.
- Telegram receives a useful companion lesson tied to the same campaign.
- Draft edits revoke approval and prevent stale scheduled publishing.
- No duplicate DM is sent for a repeated event; unknown provider outcomes are not blindly retried.
- Comment automation uses official connected-account capabilities and respects messaging limits.
- No forced follow, spam, fabricated claims, or unverified links.
- All provider credentials remain outside source control and logs.
- Unit/integration tests pass; a real-account test is recorded separately from mocked CI.

## Non-goals for v1

- Paid API dependence as a hard requirement.
- Unofficial Instagram scraping or browser automation.
- Guaranteed virality or guaranteed follower conversion.
- Automated follow/unfollow, mass comments, or unsolicited DMs.
- Publishing unreviewed AI-generated factual claims.
