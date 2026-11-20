# MR_SIAVASH_EL_AGENT — Device Companion Operations

## Product boundary

MR_SIAVASH_EL_AGENT is the device-facing companion layer. It delegates reasoning, private memory, task state, scheduling, policy, approvals, and audit to MR_SIAVASH_HUB_AI. It does not implement a second AI orchestrator.

## Supported targets

| Target | Planned runtime | Initial responsibility |
|---|---|---|
| Windows 11 | Local companion service | Device enrollment, heartbeat, explicit screenshot request, allowlisted app launch |
| Android | Native Kotlin companion | Permission-mediated actions and device status |
| Browser | Extension | Allowlisted tab and page workflows |
| Cloud | Hub worker/scheduler | Durable scheduling and coordination, not covert access to personal devices |

Windows is the first implementation target. Android, browser, and cloud capabilities remain planned until their own code and tests exist.

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

The separate [MR_SIAVASH_EL_AGENT repository](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_EL_AGENT) contains the local Windows companion MVP. It provides a loopback-only API, local bearer-token authentication, explicit screenshot capture, a fixed application-launch allowlist, SQLite-backed scheduled app launches, and owner-initiated Hub pairing with the `device.heartbeat` scope. It sends minimal outbound heartbeat metadata only; it does not yet accept Hub-issued remote tasks or share Hub memory.

Use the companion's own README for installation and operation. Its local API token is not a Hub credential and must never be forwarded through the public website or a network tunnel.

## Hub integration sequence

1. Owner-created single-use pairing, owner-scoped device registry, hashed short-lived credentials, scoped access, listing, revocation, and authenticated heartbeat are merged into Hub `main`.
2. Migration 50 persists bounded heartbeat runtime diagnostics. PR #456 merged as [`ba0cc727`](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_HUB_AI/commit/ba0cc7278cc94badfaeb0ef566023cd80112f6fb). Heartbeat metadata is device-reported diagnostics, not proof of task execution.
3. Migration 51 and device-task dispatch are merged to Hub main in PR #460 (merge commit `4d030f0abc28e9a63e4fc026243ef74c906e8769`). They provide scheduled, owner-scoped, idempotent tasks; one-at-a-time device claims; short-lived hashed leases; bounded action schemas; explicit screenshot confirmation; audit events; queue limits; cancellation before claim; expiry and revocation fencing.
4. The initial remote action set is only `app.launch` for a fixed application allowlist and explicitly confirmed `screen.capture`. Arbitrary shell, file paths, URLs, keystrokes, and model-authored executable payloads are not accepted.
5. Device outcomes are recorded as `reported_succeeded` or `reported_failed` with `outcome_verified=false`. An expired claim or revoked device becomes `unknown_outcome` and is never automatically replayed.
6. The Windows companion integration is under review in EL_AGENT PR #8. That branch adds scoped task polling/claim, outcome reporting, and Windows Credential Manager storage with legacy plaintext migration; exact-head CI and live Hub deployment/physical-device acceptance remain gates. Its standalone local token is not interchangeable with a Hub credential.
7. Shared Hub memory, Android companion, and browser extension remain separate milestones.

## Current status

- Architecture decision and typed contracts: merged into Hub main.
- Hub pairing registry, single-use challenge exchange, hashed access/refresh credentials, scoped heartbeat authentication, owner listing/revocation, and audit events: merged into Hub main.
- Migration 50 heartbeat runtime metadata: merged as `ba0cc727`; exact PR-head checks passed and post-merge Backend CI passed.
- Bounded device task dispatch: merged through PR #460 as `4d030f0abc28e9a63e4fc026243ef74c906e8769`. Post-merge Backend CI, main CI, Windows Launcher Validation, Video Render Integration, Defensive Python Scan, Workflow Security Audit, and OpenSSF Scorecard all passed.
- The dispatch API is not yet exposed through AgentOrchestrator tools. Do not let model output self-approve screenshot capture or directly authorize device actions; an approval-aware adapter and EL_AGENT client are separate gates.
- Standalone Windows MVP: EL_AGENT PR #8 adds a Hub task consumer limited to allowlisted `app.launch` and explicitly owner-confirmed `screen.capture`, plus Windows Credential Manager storage. Its earlier exact-head Linux/Windows Python 3.11/3.12 matrix and Android build passed; follow-up vault changes are undergoing a fresh CI run. Do not treat remote tasks as live until PR #8 is merged, the Hub deployment is verified, and physical Windows acceptance succeeds.
- Hub staging Worker: no `mr-siavash-hub-gateway-staging` Worker is deployed. The isolated source config is not a deployment. Deployment needs a dedicated least-privilege provider token and a separate Hub-to-gateway bearer secret in the Hub server-side secret store; never reuse the ChatGPT Cloudflare connector credential.
- Shared Hub memory is owner-scoped and supports export/deletion, FTS5 retrieval, provenance and freshness metadata. Dreaming remains a read-only duplicate-review proposal process; it does not silently rewrite or delete memory.
- Android companion and browser extension: not yet implemented.
