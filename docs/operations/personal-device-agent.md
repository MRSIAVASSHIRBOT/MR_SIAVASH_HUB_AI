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

The separate [MR_SIAVASH_EL_AGENT repository](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_EL_AGENT) contains the first local Windows companion MVP. It provides a loopback-only API, local bearer-token authentication, explicit screenshot capture, a fixed application-launch allowlist, and SQLite-backed scheduled app launches. It deliberately does not yet pair with Hub, share Hub memory, or accept remote commands.

Use the companion's own README for installation and operation. Its local API token is not a Hub credential and must never be forwarded through the public website or a network tunnel.

## Hub integration sequence

1. Owner-created single-use pairing, owner-scoped device registry, hashed short-lived credentials, scoped access, listing, revocation, and authenticated heartbeat are merged into Hub `main`.
2. Migration 50 persists bounded heartbeat runtime diagnostics. PR #456 was merged as [`ba0cc727`](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_HUB_AI/commit/ba0cc7278cc94badfaeb0ef566023cd80112f6fb). Heartbeat data remains device-reported diagnostics, not proof of task execution.
3. The current device-task-dispatch branch adds an allow-listed task queue, owner-bound idempotency, short leases, device-scope checks, explicit confirmation for screenshots, cancellation before claim, expiry, and self-reported outcomes. It is not available on `main` until its PR and exact-head CI pass.
4. Integrate the Windows companion only after its enrollment client, secure credential-vault storage, renewal, task claim/outcome protocol, and revocation behavior are implemented and tested. Its standalone local token is not interchangeable with a Hub credential.
5. Shared Hub memory, Android companion, and browser extension remain separate milestones.

## Device task safety contract

The initial remote action set is deliberately limited to `app.launch` for the fixed applications `notepad`, `calculator`, `explorer`, `browser`, and `chatgpt`, plus `screen.capture` after explicit owner confirmation. Arbitrary shell commands, arbitrary URLs, arbitrary file paths, and model-authored executable payloads are not accepted.

The Hub checks the owner's active device registration and the exact granted scope before queuing. A device claims one task at a time using a short-lived random lease; only its hash is stored. A task whose lease expires becomes `unknown_outcome` and is never automatically replayed. Owners can cancel queued tasks; a claimed task returns a conflict because remote cancellation cannot yet be guaranteed. Device completion is recorded as `reported_succeeded` or `reported_failed`, with `outcome_verified=false`: a device report is not independent proof that the requested operation occurred.

## Current status

- Architecture decision and typed contracts: merged into Hub main.
- Hub pairing registry, single-use challenge exchange, hashed access/refresh credentials, scoped heartbeat authentication, owner listing/revocation, and audit events: merged into Hub main.
- Migration 50 heartbeat runtime metadata: merged as `ba0cc727`; exact PR-head checks passed. Post-merge CI was still running at the last check.
- Bounded device task dispatch: implementation branch `feat/device-task-dispatch-20261120`; migration 51 and API/repository/tests are in progress and require full hosted CI before merge.
- Standalone Windows MVP: implemented in the separate repository; hosted CI passed on `98e77d4b9ef0684e60281297891c5d22ddb60749` ([run 44726855003](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_EL_AGENT/actions/runs/44726855003)); live Windows install/upgrade/backup/restore/rollback acceptance remains pending.
- Staging Worker configuration exists in source, but no `mr-siavash-hub-gateway-staging` Worker is deployed. Deployment and authenticated acceptance require the owner's dedicated least-privilege Cloudflare API token and separate Hub-to-gateway bearer secret; the ChatGPT Cloudflare connector credential must not be reused.
- Shared Hub memory is implemented with owner scoping, export/deletion, FTS5 retrieval, provenance and review metadata. Dreaming currently produces read-only duplicate-review proposals; it does not automatically rewrite or delete memory.
- Android companion and browser extension: not yet implemented.
