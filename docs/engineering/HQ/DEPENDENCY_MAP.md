# MR_SIAVASH_ENGINEERING_HQ — Dependency and Integration Map

**Baseline date:** 2026-11-21  
**Rule:** independent repositories integrate through versioned, authenticated contracts. No direct cross-repository database access.

## System ownership

| Capability | Authoritative owner | Consumers |
| --- | --- | --- |
| Owner identity and sessions | HUB | EL_AI through paired client identity |
| Private memory and retrieval | HUB | EL_AI through scoped Hub API |
| Policy, grants and approval | HUB | Hub tools, Agent, EL_AI task submission |
| Agent orchestration and model routing | HUB | HUB operator UI and approved clients |
| Durable tasks, jobs and workflow state | HUB | EL_AI and operator UI through API |
| Private media assets and processing | HUB | HUB operator UI and approved workflows |
| Public website and learning experience | Website | Public visitors |
| Public assistant Gateway | Website | Website and EL_AI public assistant client |
| Public Hub status projection | HUB defines the public contract; Website renders it | Website |
| Telegram transport and command routing | EL_AI | Telegram owner/public users under explicit policy |
| Cloudflare Worker deployment | Each repository owns its own Worker/release | No implicit shared ownership |

## Current integration edges

### 1. EL_AI → HUB private API

**Status:** source integration exists; live runtime acceptance is not verified.

- EL_AI uses a paired client identity and scoped credential.
- Hub pairing, scope enforcement, revocation, task submission, status/history and bounded plan operations exist in source.
- Hub remains authoritative for policy and task authorization.
- EL_AI Hub integration is opt-in and must remain disabled unless explicitly configured.
- EL_AI PR #78 adds an explicit no-redirect guard to the authenticated Hub client. Its exact-head CI and security audit passed; merge remains a separate review decision.

Required contract properties:
- HTTPS for explicitly enabled remote Hub connections; loopback is preferred for local development.
- No redirect following for authenticated requests.
- Least-privilege scopes, expiry, refresh rotation and revocation.
- Request correlation and stable idempotency keys.
- Bounded timeouts, response sizes, retry/backoff and sanitized errors.
- No direct Hub database or local filesystem access from EL_AI.

### 2. EL_AI → Website public Gateway

**Status:** public client integration exists in source; live bot/Gateway acceptance is not verified.

- The Website owns the public Gateway contract.
- EL_AI may send only the current public message and approved public request metadata.
- Private Hub memory, owner messages, task records, credentials and private context must never cross this edge.
- Public and owner message-routing paths must remain isolated.

Acceptance:
- Contract/schema tests on both sides.
- Tests proving private owner content and Hub task results never reach the public Gateway or public Telegram replies.
- Explicit public mode enablement and bounded quota/rate controls.
- Live test only after owner-managed runtime configuration is available.

### 3. HUB → Website public status projection

**Status:** source contract/schema and Website consumer exist; freshness and compatibility need continuous verification.

- HUB owns the data projection and its schema.
- Website owns presentation and cache behavior.
- The public projection must contain allow-listed, non-sensitive metadata only.
- Unknown, stale or missing status must never be rendered as healthy.
- Do not expose private task content, local paths, account identifiers, secrets or internal diagnostics.

Acceptance:
- Schema validation in both repositories.
- Version compatibility tests.
- Freshness timestamp and bounded response envelope.
- Failure behavior that preserves the public site while marking the status unavailable/stale.

### 4. HUB → local and remote model/tool providers

**Status:** provider abstractions and policy gates exist in source.

- HUB owns provider registry, capability matching, tool permissions and execution policy.
- Local inference is opt-in and bounded.
- Remote providers require explicit selection and configuration; no silent fallback.
- Tool side effects require grants and/or explicit approval according to risk.
- Provider errors must be sanitized and correlated without logging credentials or private payloads.

Acceptance:
- Provider capability mismatch tests.
- Timeout, cancellation, budget, idempotency and unknown-outcome tests.
- No paid or remote call begins from preview or evaluation alone.

## Cross-cutting contracts

| Concern | Required behavior |
| --- | --- |
| Authentication | Scoped service identity; no shared browser credentials |
| Authorization | Enforced by the owning service at execution time |
| Versioning | Explicit API/schema version; compatibility tests before consumer upgrades |
| Correlation | Stable request/trace identifier propagated across service calls |
| Idempotency | Stable operation key for retried state-changing requests |
| Retry | Bounded exponential backoff only for explicitly safe operations |
| Timeouts | Finite connect/read/overall deadlines |
| Privacy | Public/private context separation; minimum metadata only |
| Errors | Stable error codes, sanitized messages, no secret or payload leakage |
| Observability | Structured events with owner/project/request correlation and redaction |
| Resilience | Partial failure isolation; unavailable is not healthy |
| Release | Independent deployment and rollback per repository |

## Dependency sequence

1. Stabilize HUB auth, policy, jobs, pairing and public projection contracts.
2. Review and merge safe EL_AI client hardening only after exact-head CI and independent QA.
3. Validate Website public contract compatibility without introducing direct private Hub access.
4. Run local integration tests with synthetic/test identities.
5. Perform live staging tests only after explicit resource and credential approval.
6. Keep production release gates independent for each repository.

## Explicit non-goals

- No shared database across repositories.
- No direct EL_AI access to HUB SQLite/D1 or private filesystem.
- No Website access to private Hub memory or owner task context.
- No implicit remote model fallback or paid provider invocation.
- No Gshop integration or operations within this workspace.
- The separate MR_SIAVASH_EL_AGENT device companion repository is not included in this three-repository baseline and must be audited separately before work is assigned to it.


# Four-project ownership and integration correction — 2026-11-21

This section supersedes the earlier three-repository map and the former statement that EL_AGENT was excluded.

## Four-project ownership matrix

| Project | Primary responsibility | Owns | Must not own |
| --- | --- | --- | --- |
| MR_SIAVASH_HUB_AI | Central intelligence/control plane | Ecosystem identity, cross-project policy/grants, approvals, shared memory services, durable shared tasks/workflows, device registry, audit, provider/tool governance | Local OS execution or platform-specific device UI |
| MR_SIAVASH_EL_AGENT | Personal desktop/device execution | Standalone local runtime, Windows/Android adapters, local settings/scheduler, device capability execution, local credential storage, future local memory | Telegram transport, central ecosystem identity, public website, independent authority to expand grants |
| MR_SIAVASH_EL_AI | Telegram-facing assistant and communication | Telegram updates, conversational routing, scoped Hub client, public/owner conversation separation | Direct Windows/Android execution, local device credentials, central policy authority |
| MR_SIAVASH_AI | Public website and Gateway | Public UI/content, public assistant Gateway, public status presentation | Private Hub memory, owner task data, device credentials, local device operations |

## Integration edges and current evidence

### HUB ↔ EL_AGENT — paired device control plane

**Status:** heartbeat/pairing is on EL_AGENT main; bounded remote task consumers are in Draft PRs #23 (Windows) and #25 (Android).

- EL_AGENT main has owner-initiated Hub pairing, short-lived rotating device credentials and outbound minimal heartbeat metadata.
- EL_AGENT main does not yet implement Hub-issued remote task dispatch.
- PR #23 adds Windows foreground task claiming/execution with exact device identity, scopes, owner confirmation, credential vault and unknown-outcome handling. CI passed; physical Windows 11 and isolated Staging acceptance remain pending.
- PR #25 adds Android foreground task claim/review, Android capability policy, app aliases, serialized credential lifecycle/Unpair fences, planner, local model runtimes and provider routing. Python CI and Android build/unit tests passed on exact head; physical-device and Staging acceptance remain pending.
- HUB owns task issuance, lease, grant, revocation and reconciliation. EL_AGENT owns local platform capability checks and execution result.
- EL_AGENT remains operational locally when HUB is disconnected. Hub integration must be opt-in, versioned, scoped and revocable.

Required contract: exact paired device ID; narrow scopes; action allowlist; typed bounded payload; idempotency key; correlation ID; lease expiry/deadline; owner confirmation; cancellation fence; structured result; unknown-outcome reconciliation; bounded retries; no redirects on authenticated requests.

### EL_AI → HUB — Telegram client

**Status:** authenticated Hub client redirect hardening is merged into EL_AI main as commit `39ea955`; exact-main CI, security audit and Scorecard passed.

- EL_AI is the Telegram communication interface, not the device executor.
- It may submit owner-authorized, scoped task requests to HUB. HUB authorizes and decides whether a device task may be relayed to EL_AGENT.
- Never forward Telegram public-user content into private owner memory or private device operations without explicit identity and policy checks.

### Website ↔ HUB — public projection and Gateway

**Status:** public status schema and Gateway consumer exist in source; Website main exact-head workflows passed. Runtime source parity remains an open operational check in Website Issue #120.

- Website consumes allow-listed public status only.
- No private memory, task result, device ID beyond approved public metadata, credential, local path or owner diagnostic may enter public output.

### EL_AGENT ↔ Website — optional public integration only

No direct device-to-public-site execution path is authorized. If status presentation is needed, EL_AGENT reports only through HUB's sanitized public projection or a separately reviewed public contract. Website cannot invoke device tools.

## Four-party contract requirements

- Each service has an independent release/version and explicit API ownership.
- No cross-repository direct DB or private filesystem access.
- Authenticated clients refuse redirects; credentials are scoped, short-lived and revocable.
- State-changing calls use stable idempotency keys and request correlation IDs.
- All network calls have finite deadlines, bounded response sizes and sanitized error handling.
- Model-generated content is untrusted; deterministic policy at the execution owner authorizes every action.
- Public and private contexts remain separate.
- Missing/revoked integrations degrade to disconnected/unavailable; local EL_AGENT functions continue.
