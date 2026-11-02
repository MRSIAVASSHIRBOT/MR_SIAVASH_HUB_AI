# OpenClaw Integration Design

**Status:** Proposed integration; documentation-only initial change. No OpenClaw package is installed or executed by this repository yet.  
**Target repository:** `MR_SIAVASH_HUB_AI`  
**Upstream:** https://github.com/openclaw/openclaw  
**Upstream license:** MIT (verify the exact release and third-party notices before redistributing any upstream code).

## Decision

Treat OpenClaw as an **optional, separately managed assistant runtime** that can connect to MR SIAVASH HUB through a narrow adapter. Do not fork or embed its full runtime in the Python/FastAPI core, and do not make Node.js/OpenClaw a mandatory dependency of the existing installation.

This preserves the HUB's modular-monolith architecture and provider-agnostic core while allowing OpenClaw's channel and plugin ecosystem to be evaluated as an optional capability.

## Why it fits

OpenClaw's upstream README describes a local Gateway for sessions, tools, events, and channel connections; pluggable model providers and agent harnesses; and support for messaging channels and native clients. These overlap with the HUB's agent, model, integration, and content capabilities. The overlap is useful only when ownership is explicit: the HUB remains the source of truth for HUB jobs, approvals, audit records, and recovery.

## Proposed boundary

- **HUB owns:** authenticated API, policy evaluation, approval records, audit trail, durable jobs/workflows, idempotency, checkpoints, model-provider policy, and HUB-side task status.
- **OpenClaw owns (when installed and enabled):** its Gateway, its own sessions/state, supported chat channels, and its own plugin runtime.
- **Adapter owns:** connection health, capability discovery, input/output schema validation, request correlation, bounded timeouts, and translating approved HUB operations into the selected OpenClaw interface.
- **No shared database:** do not write directly into OpenClaw's internal storage or let OpenClaw bypass HUB APIs to mutate HUB state.
- **No implicit model routing:** an OpenClaw request must not silently switch from a local model to a remote provider, or vice versa.
- **No automatic installation:** do not download, install, launch, or update OpenClaw or its plugins automatically.

## Integration stages

### Stage 0 — Discovery and compatibility (this document)

Record the candidate and establish boundaries before runtime code is added. Confirm the chosen upstream release, supported Gateway/API contract, Windows compatibility, plugin API stability, data flow, and operational requirements.

### Stage 1 — Read-only optional connector

Add a disabled-by-default configuration section and an adapter interface. Initially support only a local health/status check and explicitly permitted read-only capabilities. Use a loopback-only endpoint by default, finite timeouts, strict response validation, and sanitized errors. If the installed OpenClaw version or API contract is unsupported, fail closed with a clear status.

### Stage 2 — Approved task bridge

If Stage 1 passes tests, allow OpenClaw to submit a narrowly scoped task to the HUB through authenticated HUB APIs. The HUB validates the request, creates a durable job with an idempotency key, and applies existing policy and approval requirements. OpenClaw must not execute a HUB job directly or bypass the worker.

### Stage 3 — Explicitly approved outbound actions

Only after the earlier stages pass, consider selected channel notifications or content publishing. External sends are side effects: require destination allowlists, duplicate-send protection, audit events, and an approval gate where policy requires it. Never replay an action automatically when its external outcome is unknown; mark it for reconciliation/manual review.

### Stage 4 — Optional plugin bridge

Evaluate a small, pinned OpenClaw plugin only if a concrete capability cannot be delivered cleanly through the adapter. Review its source, license, permissions, update path, and compatibility before enabling it. Plugin installation and activation must remain explicit operator actions.

## Security and privacy requirements

1. Keep the connector disabled unless the owner explicitly configures it.
2. Bind local communication to loopback by default; do not expose a Gateway to the public internet as part of setup.
3. Authenticate every HUB API call and keep credentials out of logs, prompts, audit payloads, and repository files.
4. Treat messages from Discord, Slack, Telegram, WhatsApp, and other channels as untrusted input.
5. Give the bridge least privilege; no arbitrary shell, filesystem, browser, or unrestricted tool access.
6. Do not trust community plugins by default. Pin versions and inspect provenance before installation.
7. Require policy evaluation and owner approval for sensitive or external side effects.
8. Use bounded timeouts, response-size limits, rate limits, schema validation, and sanitized errors.
9. Keep OpenClaw memory/session data separate from HUB memory unless a later, explicit data contract defines what may be shared.
10. Provide a one-step disable switch and ensure disabling the connector does not affect core HUB functions.

## Configuration sketch (not active configuration)

Use environment/config settings only; never commit real credentials.

- `MRH_OPENCLAW_ENABLED=false`
- `MRH_OPENCLAW_BASE_URL=http://127.0.0.1:<configured-port>`
- `MRH_OPENCLAW_CONNECT_TIMEOUT_SECONDS=<small bounded value>`
- `MRH_OPENCLAW_REQUEST_TIMEOUT_SECONDS=<bounded value>`
- Credentials, if required by the verified upstream contract, must be supplied through the existing secret mechanism and must never be stored in this document.

The port, authentication mechanism, and exact API paths are intentionally unresolved until the chosen OpenClaw release and its official documentation are checked. Do not guess these values or assume that a generic HTTP endpoint is enabled.

## Acceptance criteria before enabling Stage 1

- Core HUB tests pass with OpenClaw absent and the connector disabled.
- Disabled or unconfigured connector makes no network requests and starts no external processes.
- Only loopback URLs are accepted by default; redirects and unexpected destinations are rejected.
- Authentication failures, timeouts, malformed payloads, and unsupported versions fail closed.
- Logs and errors contain no tokens, credentials, or full sensitive message bodies.
- No direct database coupling exists between the two systems.
- The connector cannot execute tools or publish messages beyond its explicit allowlist.
- An unknown outcome for an external side effect is never blindly retried.
- Documentation explains manual installation, configuration, health checks, and complete disablement.
- A reviewed, pinned upstream version and license/third-party notice check are recorded before release.

## Current decision record

- **Recommendation:** integrate through an optional adapter, not by merging the OpenClaw source into the HUB core.
- **Initial implementation scope:** discovery and design only; this commit does not claim a working runtime integration.
- **Next engineering step:** inspect the current HUB integration/provider contracts and official OpenClaw Gateway/API documentation for a specific pinned release, then implement Stage 1 on this feature branch with tests.
- **Upstream references:**
  - https://github.com/openclaw/openclaw
  - https://docs.openclaw.ai/plugins/building-plugins
  - https://docs.openclaw.ai/start/why-openclaw
