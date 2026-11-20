# ADR-0011 — Personal Device Agent Control Plane

- **Status:** Accepted
- **Date:** 2026-11-20
- **Owners:** MR_SIAVASH_HUB_AI / MR_SIAVASH_EL_AGENT
- **Related systems:** MR_SIAVASH_EL_AI, MR_SIAVASH_AI

## Context

The MR_SIAVASH ecosystem needs a personal digital representative that can coordinate approved work across Windows, Android, browsers, and cloud services. Existing projects already own distinct responsibilities:

- **MR_SIAVASH_HUB_AI** owns identity, private memory, task orchestration, policy, approvals, tool grants, audit, and bounded execution.
- **MR_SIAVASH_EL_AI** owns Telegram transport, Telegram identity, command routing, and user-facing Telegram delivery.
- **MR_SIAVASH_AI** owns the public website and public-knowledge Gateway.
- **MR_SIAVASH_EL_AGENT** is the product name for the device-facing execution layer; it is not a second reasoning engine or a replacement for the Hub.

The Hub architecture is a local-first modular monolith. Device execution must preserve that boundary and avoid a premature microservice split.

## Decision

1. Implement device identity, enrollment, policy, task dispatch, and audit as Hub-owned capabilities.
2. Implement a separately installed, least-privilege companion runtime for each supported device platform. The first runtime target is Windows; Android and browser companions follow.
3. Treat a device's reported capabilities as descriptive metadata only. They never grant permissions.
4. Require owner-initiated, short-lived, single-use pairing. Store only hashes of pairing and bearer credentials. Issue short-lived access credentials with explicit scopes and revocation.
5. Bind every device action to an authenticated owner, paired device, declared capability, policy decision, bounded input schema, timeout, and audit correlation ID.
6. Keep arbitrary shell execution, unrestricted filesystem access, unrestricted browser control, hidden monitoring, credential extraction, and silent privilege escalation out of scope.
7. Use OS-native consent and visible interaction for screen capture, accessibility, notifications, and other sensitive platform APIs.
8. Keep high-impact actions (external messages, public publishing, destructive file/repository changes, account/security changes, and financial actions) behind explicit approval bound to exact action parameters.
9. Reuse Hub task, policy, approval, memory, scheduler, and audit services. Do not create competing databases or duplicate orchestration in EL_AI.
10. Integrate the dashboard in MR_SIAVASH_AI only through an authenticated, documented boundary; never expose Hub credentials in browser storage or public Gateway endpoints.

## Initial delivery sequence

- **D0 — Contract foundation:** typed device/platform/capability and heartbeat contracts, architecture and threat-boundary documentation.
- **D1 — Pairing and registry:** owner-created single-use challenge, hashed token storage, device listing, revocation, and audit.
- **D2 — Windows companion:** explicit local install, secure Hub pairing, heartbeat, screenshot capture on request, and allowlisted app launch.
- **D3 — Task bridge:** Hub-issued bounded jobs, device acknowledgement, cancellation, expiry, idempotency, and outcome verification.
- **D4 — Scheduler:** durable schedules, missed-run policy, timezone handling, retry limits, and device-online requirements.
- **D5 — Android and browser:** native Android companion and browser extension with platform permission boundaries.
- **D6 — Adaptive representative:** owner-approved preference learning, procedural memory, and bounded multi-step planning.

## Security and privacy requirements

- Deny by default; each device receives only owner-approved scopes.
- Device credentials are opaque, short-lived, revocable, and stored as hashes server-side.
- Pairing codes are single-use, expire quickly, and are bound to one owner and one device identity.
- Heartbeats contain only bounded operational metadata; no screenshots, message contents, keystrokes, or browsing history are sent implicitly.
- Screen capture is explicit per task, visible to the local user, and subject to OS permission.
- All device actions are auditable; logs exclude raw credentials, screenshots, and private content.
- Remote access is disabled by default. Local loopback is the initial Windows mode; remote mode requires an explicit secure transport and deployment review.
- Model output and device-supplied content are untrusted. Neither can create permissions or override policy.

## Alternatives considered

- **Build a separate AI brain in EL_AGENT:** rejected because it duplicates Hub orchestration, policy, memory, and audit.
- **Put desktop automation into EL_AI's Telegram process:** rejected because Telegram transport and device execution have different lifecycle, trust, and platform requirements.
- **Expose a public website endpoint to control devices:** rejected because the public Gateway must not become a private control plane.
- **Allow unrestricted computer-use tools:** rejected because they create excessive authority and poor auditability.

## Consequences

- Hub remains the single authority for private identity, permissions, tasks, approvals, and audit.
- Device companions can be developed and updated independently while sharing versioned contracts.
- The first usable release is intentionally narrower than the final product: enrollment and read-only heartbeat precede computer-control actions.
- A device being online does not imply that every capability is enabled or authorized.

## Review triggers

Revisit this decision before enabling remote device control, persistent unattended screen capture, arbitrary command execution, multi-user hosting, or public exposure of device APIs.
