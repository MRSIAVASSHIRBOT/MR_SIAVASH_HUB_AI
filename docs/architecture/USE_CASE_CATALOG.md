# Ecosystem Use-Case Catalogue — G3

- **Date:** 2026-11-27
- **Status:** Initial actor and journey baseline; detailed UI/API sequence diagrams are implementation follow-ups.
- **Portfolio:** HUB, EL_AI, EL_AGENT, MR_SIAVASH_AI
- **Authority:** [ADR-0047](decisions/ADR-0047-four-product-ecosystem-scope-and-telegram-ownership.md)

## 1. Actors

| Actor | Description | Trust boundary |
|---|---|---|
| Owner | Primary ecosystem owner; can initiate private tasks and manage grants | Strong identity verification and explicit approval for sensitive actions |
| Public visitor | Unauthenticated or public-only visitor of MR_SIAVASH_AI | Public data and public Gateway only |
| Learner | Visitor using learning content and browser-local progress | Public content and data local to the browser profile |
| Paired Telegram owner | Owner using EL_AI through an identity-bound Telegram account | Owner-only scopes, revocable HUB pairing |
| Device owner | Person physically/locally controlling Windows or Android EL_AGENT | Local OS identity, local grants and per-action confirmation |
| Authorized service | One of the four products making a scoped API/event call | Service identity, contract version, scope, request/trace metadata |
| Business/customer contact | Optional future Telegram Business customer actor, only when explicitly enabled | Separate customer context; never owner authority |
| Operator/maintainer | Authorized person maintaining a specific repository or runtime | Repository/environment-specific permissions; no implicit production access |

## 2. Use-case index

| ID | Use case | Primary actor | Main products |
|---|---|---|---|
| UC-01 | Convert a natural-language goal to a Work Order and plan | Owner | EL_AI → HUB |
| UC-02 | Execute and verify a durable workflow | Owner | HUB |
| UC-03 | Converse with the owner through Telegram | Paired Telegram owner | EL_AI, HUB |
| UC-04 | Recover an ambiguous Telegram delivery outcome | Paired Telegram owner / EL_AI runtime | EL_AI |
| UC-05 | Execute an approved local Windows/Android action | Device owner | EL_AGENT |
| UC-06 | Use EL_AGENT while HUB/network/cloud are unavailable | Device owner | EL_AGENT |
| UC-07 | Pair/revoke EL_AGENT with HUB for optional task relay | Owner | HUB, EL_AGENT |
| UC-08 | Ask a public Website assistant question | Public visitor | MR_SIAVASH_AI |
| UC-09 | Use public learning and browser-local workspace | Learner | MR_SIAVASH_AI |
| UC-10 | Publish/manage public content or support operations | Authorized owner/operator | HUB and/or Website according to contract |
| UC-11 | Register or invoke a capability/tool | Owner / authorized service | HUB |
| UC-12 | Review audit, evidence, release and project health | Owner / maintainer | HUB and all four products |

## 3. Primary and exception flows

### UC-01 — Goal to Work Order

**Preconditions:** Owner identity is verified; EL_AI or HUB interface is available; no consequential execution occurs merely from interpreting the request.

**Main flow:**
1. Owner states a goal, constraint or question.
2. EL_AI identifies intent and resolves only safe contextual ambiguity.
3. EL_AI sends a bounded request to HUB with actor identity, permitted context and request ID.
4. HUB creates a structured Work Order with scope, assumptions, dependencies, risks, acceptance criteria and verification plan.
5. HUB returns a preview for owner review.
6. Owner accepts, edits or rejects the plan.

**Exceptions:** Missing material detail → ask one focused question; untrusted prompt asks for disallowed capability → reject; unavailable HUB → explain and preserve a safe local draft; unsupported contract version → fail clearly.

**Acceptance:** Work Order is schema-valid, owner-scoped, bounded and does not execute actions before explicit approval where required.

### UC-02 — Durable workflow execution and evidence

**Preconditions:** Approved Work Order, authorized tool grants and bounded execution budget.

**Main flow:** HUB validates the plan → schedules permitted steps → workers execute with idempotency/correlation → checkpoints persist → evaluator compares trusted evidence with acceptance criteria → HUB reports completion, partial completion or blocker.

**Exceptions:** Worker crash, timeout, tool denial, expired grant, duplicate dispatch, cancellation, stale/conflicting evidence and unknown external outcome.

**Acceptance:** Restart and recovery preserve state; revoked authority blocks subsequent steps; model self-report alone cannot mark completion; all results link to evidence.

### UC-03 — Owner Telegram conversation

**Preconditions:** Dedicated EL_AI bot runtime is configured; Telegram identity is bound to owner; private mode is enabled by explicit configuration.

**Main flow:** EL_AI accepts update → validates and deduplicates update → resolves owner actor → constructs bounded conversation context → routes public vs private request → calls HUB only with scoped authorization → builds response → sends through Telegram adapter → records delivery outcome.

**Exceptions:** Unknown Telegram identity → deny owner command; private chat required but absent → do not execute; HUB unavailable → safe degraded response; rate limit → bounded backoff; send timeout → mark outcome unknown unless confirmed; oversized response/media → deterministic chunking or safe rejection.

**Acceptance:** Duplicate update does not duplicate durable task; private context never enters public Gateway; delivery status distinguishes queued/sent/failed/unknown; no credential or private content in logs.

### UC-04 — Ambiguous Telegram delivery recovery

**Preconditions:** Message send may have been attempted but remote acknowledgement is missing.

**Flow:** EL_AI records delivery attempt and ambiguous state → does not claim success → consults only supported reconciliation evidence → retries only when idempotency/remote contract makes replay safe; otherwise surfaces unknown outcome for safe review.

**Acceptance:** No blind replay of ambiguous non-idempotent side effects; audit captures attempts without storing sensitive message bodies.

### UC-05 — Approved local device action

**Preconditions:** EL_AGENT installed and local runtime authenticated; capability is allowlisted; required owner confirmation is available.

**Flow:** Owner requests action → planner proposes a typed action → schema and local policy validate → capability and resource/time bounds are checked → owner confirms sensitive action → adapter executes → result is independently observed → local audit/state updated.

**Exceptions:** Unknown command/action, denied grant, missing confirmation, app unavailable, timeout, cancellation, provider unavailable and ambiguous external-intent return.

**Acceptance:** Model output cannot bypass deterministic policy; unknown actions fail closed; no arbitrary shell or unrestricted filesystem/network control.

### UC-06 — Standalone/offline EL_AGENT

**Preconditions:** HUB, internet or cloud provider may be unavailable.

**Flow:** Owner uses local settings, allowlisted tools, scheduler, local provider/voice or offline model; remote adapters are disabled or unavailable; local runtime continues within its local policy.

**Acceptance:** Core local use cases succeed with all ecosystem adapters disabled; no silent cloud fallback or data upload occurs.

### UC-07 — Optional HUB/EL_AGENT pairing and task relay

**Preconditions:** Owner explicitly initiates pairing and grants narrow device scopes.

**Flow:** HUB issues short-lived identity-bound pairing → EL_AGENT securely stores credential → heartbeat/device status is reported within declared metadata bounds → owner submits a typed task → HUB checks grant/policy → EL_AGENT locally rechecks policy and asks for confirmation where necessary → device returns signed/structured evidence → owner can revoke pairing.

**Exceptions:** Pairing expiry, revoked scope, device offline, stale task, replay, duplicate delivery, local policy denial and lost reply.

**Acceptance:** EL_AGENT remains functional without HUB; revocation stops new HUB-originated tasks; HUB approval does not override stricter local device policy.

### UC-08 — Public Website assistant

**Preconditions:** Public Gateway is available and user sees the data-disclosure notice.

**Flow:** Visitor submits a question → Website sends only the current disclosed prompt and permitted public context → public Gateway retrieves public sources → response contains bounded answer and validated references.

**Exceptions:** Consent absent → local/public knowledge fallback; provider/rate limit → safe unavailable response; malformed/untrusted source → exclude; private task or owner context requested → do not forward.

**Acceptance:** Public calls cannot receive HUB private memory, secrets or device execution context.

### UC-09 — Learning and local workspace

**Flow:** Learner browses public content → uses learning assessment/tool → progress is saved in the browser profile where supported → user can recover/export only supported local data.

**Exceptions:** Storage corruption, cross-tab conflict, stale service-worker asset, invalid import and quota exhaustion.

**Acceptance:** Local progress is not presented as a verified credential; invalid imports do not silently overwrite recoverable data.

### UC-10 — Content/support/admin operations

**Preconditions:** Specific module, data class and external action are enabled; authenticated role and consent/retention policy are satisfied.

**Flow:** Operator previews action → validates ownership and policy → approves consequential publication or data action → system executes through bounded adapter → audit and rollback evidence are retained.

**Exceptions:** Missing consent, inactive retention policy, revoked token, no approval, duplicate publish, rate limit or rollback failure.

**Acceptance:** Public and private workflows are separated; no publication/spending/production mutation occurs implicitly.

### UC-11 — Capability registration and invocation

**Flow:** Maintainer registers versioned manifest → schema and permission metadata validate → HUB assesses trust/risk and issues grants → request selects capability → deterministic policy checks scope/actor/resource → bounded execution → output validated and audited.

**Exceptions:** Unknown capability/version, permission escalation, schema drift, timeout, malformed output, dependency unavailable.

**Acceptance:** Discovery is not authorization; tool output cannot grant itself permissions.

### UC-12 — Portfolio/evidence review

**Flow:** Owner selects a product/phase → dashboard reads exact source, CI and integration evidence → evidence freshness and version are shown → risks and blocked gates are listed → owner records decision.

**Acceptance:** Source, CI, live runtime, device, legal and production readiness are visibly different evidence classes.

## 4. Cross-actor safety rules

- A Telegram public/customer actor is never promoted to owner by message content, username text, forwarded messages or model inference.
- A public Website visitor cannot access private HUB context.
- A HUB-issued grant does not silently widen EL_AGENT local capabilities.
- Business/customer routes, if enabled later, use separate sessions, scopes, data and command allowlists.
- Service identity and trace IDs are metadata, never authentication.
- Unknown outcomes remain unknown until verified evidence resolves them.

## 5. Follow-up artefacts

Detailed sequence diagrams, API examples, UI state transitions, failure matrices and manual test scripts are stored with the owning product's implementation docs and linked back to these UC identifiers.
