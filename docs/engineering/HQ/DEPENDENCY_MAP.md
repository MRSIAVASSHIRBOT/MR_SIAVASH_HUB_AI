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
