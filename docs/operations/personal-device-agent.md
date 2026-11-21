# MR_SIAVASH_EL_AGENT — Device Companion Operations

## Product boundary

MR_SIAVASH_EL_AGENT is the device-facing companion layer. It delegates reasoning, private memory, task state, scheduling, policy, approvals, and audit to MR_SIAVASH_HUB_AI. It does not implement a second AI orchestrator.

## Supported targets

| Target | Current implementation status | Responsibility |
|---|---|---|
| Windows 11 | EL_AGENT PR #23 is Draft; exact-head CI passed; physical acceptance pending | Outbound Hub task polling for allowlisted app.launch and explicitly owner-confirmed local screen.capture |
| Android | EL_AGENT PR #24 is Draft and stacked on PR #20; exact-head CI passed; physical acceptance pending | Foreground-only app.launch for ChatGPT/browser with a separate on-device approval dialog |
| Browser | Planned | Allowlisted tab and page workflows |
| Cloud | Hub worker/scheduler | Durable scheduling and coordination, not covert access to personal devices |

Windows and Android task-consumer code exists in separate review branches but is not merged or live-device accepted. Browser extension remains planned. Hub API availability, companion source implementation, staging deployment, and physical-device acceptance are separate gates.

## Device identity lifecycle

1. The owner authenticates to the local Hub.
2. The owner creates a short-lived pairing challenge for a specific device identity and platform.
3. The companion exchanges the challenge once and receives scoped credentials.
4. The server stores credential hashes only; the companion stores refresh material in the platform credential vault.
5. The owner can list and revoke devices. Revocation invalidates all credentials for that device.
6. Heartbeats update liveness and carry only bounded, self-reported diagnostics. `runtime_state` (`ready`, `busy`, or `degraded`), `app_uptime_seconds` (0–31,536,000), and an optional `last_task_id` UUID are operational hints, not proof that a task ran or completed. Device-reported capabilities are descriptive and do not grant authority.

## Execution contract

A future device task must include a task ID, device ID, action name, schema-validated parameters, required scope, policy decision, expiry, idempotency key, timeout, and audit correlation ID. The companion must reject unknown actions and expired tasks. It must report a structured outcome; the Hub must not equate dispatch with successful completion.

## Initial action policy

| Action | Initial policy |
|---|---|
| Device status / heartbeat | Allowed with paired device scope |
| Screenshot | Explicit user task, visible capture, OS permission |
| Launch an allowlisted application | Reversible local action with a narrowly scoped grant |
| Read arbitrary files | Disabled until a path-scoped design and review exist |
| Write/delete files | Approval and preview required |
| Browser form submission / external message | Exact action preview and approval |
| Arbitrary shell / scripts | Not supported |
| Credential extraction / covert monitoring | Prohibited |

## Reliability

- Heartbeats are rate-limited and bounded.
- Device and task IDs are stable UUIDs.
- Dispatch and completion are idempotent where possible.
- Offline devices do not receive a false success state.
- Expired tasks are not replayed automatically.
- Retries are limited to explicitly idempotent operations.
- Local companion logs exclude credentials and captured content.
- Every operation has cancellation and timeout semantics before production use.

## Standalone Windows MVP

The separate [MR_SIAVASH_EL_AGENT repository](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_EL_AGENT) contains the Windows and Android companion implementations. Draft PR #23 adds an outbound Windows Hub task consumer for fixed app.launch aliases and explicitly owner-confirmed local screen.capture, with Windows Credential Manager storage and fail-closed credential migration. Draft PR #24 adds a foreground-only Android consumer for ChatGPT/browser app.launch with an explicit approve/reject dialog. Neither PR is merged or accepted on a physical device. The local companion API token remains distinct from Hub credentials and must never be forwarded through the public website or a network tunnel.

Use the companion's own README for installation and operation. Its local API token is not a Hub credential and must never be forwarded through the public website or a network tunnel.

## Hub integration sequence

1. Owner-created single-use pairing, owner-scoped device registry, hashed short-lived credentials, scoped access, listing, revocation, and authenticated heartbeat are merged into Hub `main`.
2. Migration 50 persists bounded heartbeat runtime diagnostics. PR #456 merged as [`ba0cc727`](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_HUB_AI/commit/ba0cc7278cc94badfaeb0ef566023cd80112f6fb). Heartbeat metadata is device-reported diagnostics, not proof of task execution.
3. Migration 51 and device-task dispatch are merged to Hub main in PR #460 (merge commit `4d030f0abc28e9a63e4fc026243ef74c906e8769`). They provide scheduled, owner-scoped, idempotent tasks; one-at-a-time device claims; short-lived hashed leases; bounded action schemas; explicit screenshot confirmation; audit events; queue limits; cancellation before claim; expiry and revocation fencing.
4. The initial remote action set is only `app.launch` for a fixed application allowlist and explicitly confirmed `screen.capture`. Arbitrary shell, file paths, URLs, keystrokes, and model-authored executable payloads are not accepted.
5. Device outcomes are recorded as `reported_succeeded` or `reported_failed` with `outcome_verified=false`. An expired claim or revoked device becomes `unknown_outcome` and is never automatically replayed.
6. The Windows consumer is under review in [EL_AGENT PR #23](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_EL_AGENT/pull/23), based on EL_AGENT `main`, at head `ebd67e2605e26e0763f02a294aedbc511e89f1b1`. Its nine observed exact-head checks passed, including Windows/Linux Python 3.11/3.12 tests and the Android debug build; physical Windows 11 pairing, allowlisted launch, local screenshot, expiry, and revocation acceptance remain pending. The Android foreground consumer is [EL_AGENT PR #24](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_EL_AGENT/pull/24), at head `61627e6b93f17f5c9d68b2a816f6903d3710e32d`; all five observed checks passed, including Android debug build, but it is stacked on `feat/android-visual-refresh-20261120` and must not be retargeted to `main` until its preceding Android stack is merged. Physical Android approval/expiry acceptance remains pending. Both consumers still require isolated Hub Staging deployment and owner-device acceptance.
7. Shared Hub memory, Android companion, and browser extension remain separate milestones.

## Current status

- Architecture decision and typed contracts: merged into Hub main.
- Hub pairing registry, single-use challenge exchange, hashed access/refresh credentials, scoped heartbeat authentication, owner listing/revocation, and audit events: merged into Hub main.
- Migration 50 heartbeat runtime metadata: merged as `ba0cc727`; exact PR-head checks passed and post-merge Backend CI passed.
- Bounded device task dispatch: merged through PR #460 as `4d030f0abc28e9a63e4fc026243ef74c906e8769`. Post-merge Backend CI, main CI, Windows Launcher Validation, Video Render Integration, Defensive Python Scan, Workflow Security Audit, and OpenSSF Scorecard all passed.
- The bounded device dispatch API is merged through Hub PR #460. The AgentOrchestrator integration is in Hub Draft PR #465 at head `3371f2b0216ba56f431282406e2beb8b3e6ab79b`: owner-scoped `device.registry.list` and `device.app_launch.submit` tools, two independent expiring owner grants, exact device `app.launch` scope, live-grant re-checks for direct and durable Agent runs, and an atomic grant re-check inside task creation. All 21 observed exact-head checks passed. PR #465 remains Draft pending isolated Hub Staging and physical Windows/Android acceptance. Screenshot capture is not exposed to model tools; it remains an explicit owner-confirmed action through the narrow device-task API.
- Windows companion: EL_AGENT Draft PR #23 adds outbound Hub task polling/claim, outcome reporting, Windows Credential Manager storage, and allowlisted app.launch plus explicitly owner-confirmed local screen.capture. Its nine observed exact-head checks passed; physical Windows 11 acceptance remains pending. Android companion: EL_AGENT Draft PR #24 adds foreground-only ChatGPT/browser app.launch with an on-device approval dialog. Its five observed checks passed, but it remains stacked on PR #20 and is not merged to main. Neither consumer is live-device accepted.
- Hub staging Worker: the last recorded read-only inventory on 2026-11-20 reported that `mr-siavash-hub-gateway-staging` was absent. Cloudflare was not re-read on 2026-11-21, so absence is a last-recorded observation, not fresh live verification. The Website AI Gateway Preview is a separate integration and must not be repurposed; GShop resources remain excluded. The isolated source config is not a deployment. Staging remains blocked until a project-approved zone/scope decision, dedicated least-privilege provider token, and separate Hub-to-gateway bearer secret in the Hub server-side secret store are available. Never reuse the ChatGPT Cloudflare connector credential.
- Shared Hub memory is owner-scoped and supports export/deletion, FTS5 retrieval, provenance and freshness metadata. Dreaming remains a read-only duplicate-review proposal process; it does not silently rewrite or delete memory.
- Android companion preview: pairing, encrypted Keystore credentials, heartbeat, and foreground-only app.launch approval are under review in EL_AGENT PR #24 (stacked on PR #20). Physical-device acceptance remains pending. Android screenshot capture and background task dispatch are not implemented.
- Browser extension: not yet implemented.
