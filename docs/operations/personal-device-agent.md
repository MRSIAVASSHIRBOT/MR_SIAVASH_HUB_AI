# MR_SIAVASH_EL_AGENT — Device Companion Operations

## Product boundary

`MR_SIAVASH_EL_AGENT` is the device-facing companion. `MR_SIAVASH_HUB_AI` remains authoritative for owner identity, pairing, grants, task policy, scheduling, leases, revocation, and audit. The companion does not implement a second orchestrator.

## Current implementation and release state

| Component | Source state | Validation / release gate |
|---|---|---|
| Hub pairing, scoped credentials, heartbeat, device registry | Merged to Hub `main` | Source and CI evidence do not imply a deployed Hub endpoint |
| Hub task claim/complete API | Merged to Hub `main` through PR #460 | Bounded actions, hashed short-lived leases, expiry/revocation fencing, audit |
| Hub Agent device tools | Merged to Hub `main` through PR #465 | Owner grants and exact device scope are checked; Staging acceptance remains open |
| Windows task consumer | EL_AGENT PR [#23](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_EL_AGENT/pull/23), Draft | Exact-head Python matrix and Android build passed; physical Windows acceptance pending |
| Android planner and foreground task consumer | EL_AGENT PR [#25](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_EL_AGENT/pull/25), Draft | Exact-head Python matrix, Android unit tests and Debug build passed; physical Android acceptance pending |
| Windows authenticated-transport hardening | EL_AGENT PR [#26](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_EL_AGENT/pull/26), merged | Redirects are rejected to prevent bearer-token forwarding |
| Browser extension | Not implemented | Separate future milestone |

PRs #23 and #25 are each ahead of current EL_AGENT `main` and have no commits behind it at the last GitHub comparison. They remain Draft because CI cannot replace isolated Hub Staging round-trips, grant revocation/expiry checks, or physical-device acceptance. Do not merge or deploy them solely because their current CI is green.

## Device identity and credentials

1. The owner authenticates to Hub and creates a short-lived pairing challenge for one device identity and platform.
2. The companion exchanges the single-use challenge and receives credentials scoped to that paired device.
3. Hub stores credential hashes; the companion stores refresh credentials in the platform's protected credential store.
4. The owner can inspect and revoke paired devices. Revocation invalidates credentials and fences outstanding claimed tasks.
5. Heartbeats contain bounded, self-reported runtime metadata. They are liveness hints, not proof that an action ran or completed.

The Windows client rejects authenticated redirects. Android uses HTTPS-only requests and disables HTTP redirects. Local companion API credentials are distinct from Hub device credentials; neither may be exposed through the public website or a network tunnel.

## Hub task contract

Hub exposes owner-authenticated task submission, listing, inspection, and queued-task cancellation, plus device-authenticated claim and completion endpoints:

- Owner: `POST /devices/{device_id}/tasks`, `GET /devices/{device_id}/tasks`, `GET /devices/{device_id}/tasks/{task_id}`, and `DELETE /devices/{device_id}/tasks/{task_id}`.
- Paired device: `POST /devices/tasks/claim` and `POST /devices/tasks/{task_id}/complete`.

Each task is bound to an owner, paired device, exact required scope, bounded action schema, idempotency key, schedule, expiry, timeout, and audit record. A device receives one short-lived lease; Hub persists only its hash. Completion is recorded as `reported_succeeded` or `reported_failed` with `outcome_verified=false`: the device's report is not independent proof. Expired claims and revoked-device claims become `unknown_outcome` and are never replayed automatically.

## Supported action boundary

- Windows consumer PR #23: allow-listed `app.launch` and explicitly owner-confirmed local `screen.capture`.
- Android consumer PR #25: foreground-only `app.launch` for supported ChatGPT/browser aliases, with a separate on-device approve/reject step. Android does not implement screenshot capture or background task dispatch.
- Hub model tools: owner-scoped device registry listing and allow-listed app-launch submission only. They require the relevant expiring owner grants and the target device's exact `app.launch` scope. Screenshot capture is not exposed as a model tool.
- Arbitrary shell commands, scripts, executable paths, caller-provided URLs, unrestricted file access, keystroke capture, hidden monitoring, and model-authored executable payloads are not supported.

A task's dispatch or a successful local API response must never be described as verified completion. Late or ambiguous actions are not reported as success and are not retried.

## Security and reliability invariants

- Least privilege: owner grants and device scopes are independent; neither implies the other.
- Fail closed on malformed identity, credential, scope, task, lease, timeout, or response data.
- Recheck authorization at task creation and enforce lease/fencing state at completion.
- Do not persist bearer credentials or raw captured content in Hub task records.
- Queue size, action parameters, task lifetime, timeout, and execution scope are bounded.
- Revocation cancels queued tasks and fences claimed tasks as unknown outcome.
- No automatic replay after lease expiry, process interruption, or ambiguous external effect.
- Physical acceptance must verify pairing, scope boundaries, owner approval, launch behavior, expiry, revocation, and audit outcomes.

## Staging and deployment boundary

A fresh read-only Cloudflare inventory on 2026-11-22 found no dedicated `mr-siavash-hub-gateway-staging` Worker and no custom Worker domain configured for the account. The visible Workers are separate services, not an accepted Hub Staging deployment. No current Hub Staging deployment or authenticated device round-trip is claimed; no Worker, route, D1, secret, or deployment setting was changed.

Staging requires an owner-approved isolated resource scope, a dedicated least-privilege provider token, and a separate Hub-to-gateway bearer secret stored server-side. Do not reuse Website Gateway Preview, the ChatGPT Cloudflare connector credential, or any GShop resource. No production Worker deployment, live pairing, device task, screenshot, or application launch is implied by merged source or green CI.

## Acceptance sequence

1. Provision and verify an isolated Hub Staging environment under owner-controlled Cloudflare scope and credentials.
2. Run authenticated contract tests for pairing, exact scopes, task claim/complete, lease expiry, cancellation, revocation, and audit.
3. Perform Windows 11 physical acceptance for the Windows consumer.
4. Perform supported Android physical acceptance for foreground approval and app launch.
5. Keep PR #23 and #25 Draft until these gates have evidence; then re-read their exact heads and checks before any merge decision.
6. Treat production deployment as a separate owner-approved release with fresh infrastructure inventory and rollback evidence.

Shared Hub memory, Android background execution, screenshot capture on Android, and browser extension workflows remain separate milestones.
