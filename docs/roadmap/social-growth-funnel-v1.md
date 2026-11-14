# Social Growth Funnel v1 — Engineering Plan

Status: repository implementation merged into `main` on 2026-11-14; mocked CI is green on `342adddf6a25a1c17495d5235d893fdd97011fd5`. External account acceptance, provider credentials/scopes, and live publishing remain unverified and disabled.
Implementation PRs: #372 (social growth), #379 (people-needs research), #382 (research source provenance), #383 (tool/gateway security). No active PR remains for this workstream.
Current schema: research migrations 36–39, social publishing/campaign/reply migrations 40–42, Telegram task timeline migration 43, research source provenance migration 44.

## Product outcome

Build a compliant, low-cost content funnel for MR_SIAVASH_IR_BOT:
1. Research and validate a useful topic.
2. Produce an educational short-form video and a substantive companion Telegram lesson.
3. Review and approve both assets as one campaign.
4. Publish Instagram Reels and Telegram content through supported APIs.
5. Optionally reply to eligible Instagram comments with a requested resource link using the connected PostZen account.
6. Measure reach, engagement, DM delivery, Telegram joins/clicks, and content quality.

The resource CTA may politely invite the recipient to follow the page and share the post before presenting the educational link. Both actions are optional: the resource link must be delivered in the same reply regardless of whether the recipient follows or shares. Never check, infer, or claim that either action occurred. No follow-gating, share-gating, forced follows, unsolicited bulk DMs, scraping private data, or engagement manipulation. A comment-triggered private reply must comply with Meta's messaging rules and PostZen's documented limits.

## Verified repository baseline (main, 2026-11-14)

- FastAPI/SQLite owner-scoped content drafts, revision history, deduplication, explicit approval/revocation, and audit events exist.
- Durable schedules capture approved revision/hash and support cancellation.
- ContentScheduleDispatcher is integrated with WorkerEngine; worker_service runs a pull loop. Dispatch is fail-closed when provider credentials are missing.
- Telegram Bot API adapter supports text and approved JPEG/PNG/MP4 assets.
- Instagram Graph API Reels publishing is implemented alongside the existing image adapter; real-account acceptance remains unverified.
- Instagram publishing requires a professional account, Graph API credentials, and a publicly reachable signed HTTPS media origin.
- Provider delivery is not exactly-once. Ambiguous outcomes enter unknown_outcome and must be reconciled before retry.
- Video generation and the lease-fenced FFmpeg render worker register owner-scoped MP4 assets with the `video_render_cut_v1` profile. A new integration assertion verifies that the actual render-worker asset can be attached to an Instagram Reel draft; campaign creation and dispatch revalidate the same profile.
- PostZen Default profile has connected Instagram and Telegram accounts. The comment-automation inventory is empty.
- The in-repository video-generation provider registry is empty by default and currently has no configured provider. Existing local FFmpeg timeline rendering can process source footage, but prompt-to-video generation is not enabled; this remains a separate provider/local-template workstream and must not be described as operational.
- The scheduled OpenCode development workflow's latest run failed because OpenRouter returned `API key expired` for repository secret `MR_SIAVASH_HUB_AI`. The secret was not read or changed; maintainer rotation is required before scheduled AI development can resume. This failure is separate from application CI.
- Current external account credentials, Meta scopes, public media reachability, and real-account publishing have not been verified by this repository audit.

## Current implementation status (`main`, inspected 2026-11-15)

- Instagram Reels adapter: implemented with bounded polling of the same container; only a confirmed FINISHED container is published.
- Signed public media: JPEG/PNG/MP4 path and owner-scoped processed-render checks are implemented.
- Reel draft type: database migration 40 rebuilds the draft/version/schedule tables to allow `reel` while preserving existing records.
- Cross-platform campaign linkage: migration 41, owner-scoped repository, authenticated API, atomic paired scheduling, paired cancellation, and API tests are implemented.
- Existing content scheduler and worker are reused; no parallel scheduler was added.
- Resource-reply configuration: migration 42, owner-scoped persistence, authenticated GET/PUT configuration, POST preview, and operator UI are merged. Preview always includes the resource URL regardless of CTA toggles. These settings are not connected to PostZen and do not activate or send DMs.
- PostZen Instagram comment automation inventory was empty at the last external review. Hub-side settings are implemented in migration 42, but provider-side trigger creation/dispatch is not integrated; no DM is sent by this configuration.
- Main-branch CI on `342adddf6a25a1c17495d5235d893fdd97011fd5` passed Backend CI (dependency audit, lint, coverage tests), Python 3.11/3.12 CI, Windows wheel smoke, Windows launcher validation, FFmpeg render integration, defensive scan, workflow security audit, and OpenSSF Scorecard. This verifies repository code, not external account delivery.
- Live activation remains blocked until the exact keyword, final reply copy, public resource URL, target post/account, and required scopes are reviewed and explicitly approved.
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
- The reply may first invite the recipient to follow the page and share the post, using respectful, non-coercive language. The CTA is optional and must not delay or condition delivery.
- Include the educational resource URL in the same reply after the CTA. Deliver it whether the recipient follows, does not follow, shares, or does not share.
- Never query follower/share state, use those states in branching logic, or claim that a follow/share was verified. The reply helper intentionally exposes no such inputs.
- Require an absolute public HTTPS resource URL; reject placeholders, private/local URLs, and non-HTTPS destinations before configuration.
- Confirm the account has required comment and messaging scopes before activation.
- Respect one private reply per comment and platform time windows; deduplicate and cap sends.
- Create inactive/draft configuration first. Activation requires explicit review of the exact keywords, final DM copy, destination URL, account, and scope.
- User-configurable settings and preview are implemented; provider-specific PostZen trigger creation/dispatch and external acceptance tests remain future work.

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
3. Implement campaign linkage and cross-platform publishing acceptance tests. (merged; mocked CI passed on current main)
4. Implement owner-scoped customizable keyword/resource reply settings, UI, and preview. (merged; mocked CI passed; provider integration remains pending)
5. Configure one inactive PostZen comment automation for review only after keyword, DM copy, resource URL, account, and scope are approved.
6. Run a controlled test with one harmless campaign after explicit approval.
7. Enable scheduled operation only after successful acceptance and quota checks.
8. Add weekly reporting and tune topics based on observed outcomes.

## Acceptance criteria

- Reels are published only from approved owner-owned MP4 assets over verified public HTTPS.
- Telegram receives a useful companion lesson tied to the same campaign.
- Draft edits revoke approval and prevent stale scheduled publishing.
- No duplicate DM is sent for a repeated event; unknown provider outcomes are not blindly retried.
- A resource reply places the optional Follow/Share CTA before the resource URL.
- The resource URL is always included without waiting for or checking Follow/Share actions.
- No follower/share lookup, Follow-gating, Share-gating, forced follow, spam, fabricated claims, or unverified links.
- Comment automation uses official connected-account capabilities and respects messaging limits.
- All provider credentials remain outside source control and logs.
- Unit/integration tests pass; a real-account test is recorded separately from mocked CI.

## Non-goals for v1

- Paid API dependence as a hard requirement.
- Unofficial Instagram scraping or browser automation.
- Guaranteed virality or guaranteed follower conversion.
- Automated follow/unfollow, mass comments, or unsolicited DMs.
- Publishing unreviewed AI-generated factual claims.
