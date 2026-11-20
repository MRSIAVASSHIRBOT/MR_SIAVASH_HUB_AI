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

1. Owner-created single-use pairing, the owner-scoped device registry, hashed short-lived credentials, scoped access, listing, revocation, authenticated heartbeat, and pairing/revocation audit events are implemented in Hub `main`.
2. Persisted heartbeat diagnostics are proposed in [PR #456](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_HUB_AI/pull/456); they remain non-authoritative and do not indicate task success.
3. Implement Hub-issued bounded task dispatch, acknowledgement, cancellation, expiry, idempotency, and verified outcomes.
4. Integrate the Windows companion with Hub pairing only after its enrollment client, credential-vault storage, renewal, and revocation behavior are implemented and tested. Its standalone local token is not interchangeable with a Hub credential.
5. Shared Hub memory, Android companion, and browser extension remain separate future milestones.

## Current status

- Architecture decision and typed contracts: merged into Hub main.
- Hub pairing registry, single-use challenge exchange, hashed access/refresh credentials, scoped heartbeat authentication, owner listing/revocation, and audit events: merged into Hub main.
- Bounded heartbeat runtime metadata persistence: proposed in PR #456; exact-head CI is required before merge.
- Standalone Windows MVP: implemented in the separate repository; hosted CI passed on `98e77d4b9ef0684e60281297891c5d22ddb60749` ([run 44726855003](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_EL_AGENT/actions/runs/44726855003)); live Windows install/upgrade/backup/restore/rollback acceptance remains pending.
- Hub task dispatch, shared memory, Android companion, and browser extension: not yet implemented.
