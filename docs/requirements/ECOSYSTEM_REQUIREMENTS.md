# Ecosystem Requirements Catalogue — G2

- **Date:** 2026-11-27
- **Status:** Initial traceability baseline; detailed product backlog decomposition continues.
- **Scope:** HUB, EL_AI, EL_AGENT, MR_SIAVASH_AI
- **Portfolio authority:** [ADR-0051](../architecture/decisions/ADR-0051-four-product-ecosystem-scope-and-telegram-ownership.md)

## 1. Requirement semantics

- **MUST:** mandatory for the stated trust boundary or product outcome.
- **SHOULD:** expected unless an ADR records a justified exception.
- **MAY:** optional capability, not a release prerequisite unless adopted.
- Status **Baseline** means evidenced in current docs/source to some degree; it does not mean every acceptance criterion is complete.
- Every requirement needs an owner, priority, source, verification and linked implementation phase before it can be closed.

## 2. Functional requirements

| ID | Requirement | Owner | Priority | Verification / acceptance |
|---|---|---|---|---|
| FR-HUB-01 | HUB MUST transform an owner's goal into a bounded Work Order with intent, scope, assumptions, constraints, dependencies and acceptance criteria | HUB | P0 | Work Order schema/API tests; malformed and ambiguous input cases |
| FR-HUB-02 | HUB MUST plan and orchestrate durable workflows with stable step identity, state transitions, cancellation and persisted checkpoints | HUB | P0 | Worker integration, restart/recovery and cancellation tests |
| FR-HUB-03 | HUB MUST enforce policy, actor ownership, explicit scopes and approval before consequential actions | HUB | P0 | Negative authorization matrix; expiry/revocation and replay tests |
| FR-HUB-04 | HUB MUST own canonical private owner memory, workflow/task evidence and capability/tool grants | HUB | P0 | Owner isolation, provenance, export/deletion and authorization tests |
| FR-HUB-05 | HUB MUST use replaceable model/provider and tool adapters with explicit routing and budgets | HUB | P1 | Adapter contract tests; prove no hidden local-to-cloud fallback |
| FR-HUB-06 | HUB MUST evaluate completion from trusted application evidence, not model self-report | HUB | P0 | Evidence mismatch, stale/conflicting/unknown evidence tests |
| FR-HUB-07 | HUB SHOULD expose operational status, audit, cost and recovery diagnostics without leaking secret or sensitive payload values | HUB | P1 | Schema/log redaction and operator authorization tests |
| FR-ELAI-01 | EL_AI MUST maintain distinct public and owner/private actor contexts | EL_AI | P0 | Runtime routing tests proving private context never enters public requests/replies |
| FR-ELAI-02 | EL_AI MUST own the dedicated ecosystem Telegram bot, including update intake, command routing, delivery and transport lifecycle | EL_AI | P0 | Telegram adapter unit/integration tests; real test-bot acceptance remains a separate gate |
| FR-ELAI-03 | EL_AI MUST authenticate and scope HUB calls through owner-initiated pairing and revocable credentials | EL_AI + HUB | P0 | Pairing, expiry, scope, revocation, replay and client-isolation tests |
| FR-ELAI-04 | EL_AI MUST handle Telegram delivery states, duplicate updates, rate limits, bounded retries and unknown outcomes without unsafe replay | EL_AI | P0 | State-machine and failure-injection tests; unknown delivery remains distinct from confirmed delivery |
| FR-ELAI-05 | EL_AI MUST validate and normalize message/media payloads and apply bounded sizes/timeouts | EL_AI | P1 | Type/size/fuzz and invalid-envelope tests |
| FR-ELAI-06 | EL_AI SHOULD provide owner-visible task/plan status and safe pause/cancel/recovery commands where supported | EL_AI | P1 | Command authorization and lifecycle integration tests |
| FR-ELAI-07 | EL_AI MUST prevent Business/customer actors from receiving owner-only commands or permissions if such a feature is enabled | EL_AI | P1 | Cross-actor negative tests; Business routes remain disabled until product/operational acceptance |
| FR-AGENT-01 | EL_AGENT MUST operate its core local runtime without HUB, network or cloud credentials | EL_AGENT | P0 | Offline acceptance with adapters disabled and no network access |
| FR-AGENT-02 | EL_AGENT MUST restrict device actions to typed, allowlisted capabilities with schema validation, explicit owner grants and bounded execution | EL_AGENT | P0 | Deny-by-default policy tests, invalid-action and timeout tests |
| FR-AGENT-03 | EL_AGENT MUST keep model output as untrusted proposal data and authorize execution only through deterministic local policy | EL_AGENT | P0 | Prompt-injection/action-boundary tests and forged proposal tests |
| FR-AGENT-04 | EL_AGENT MUST make scheduler operations idempotent and recover interrupted tasks without blindly replaying ambiguous side effects | EL_AGENT | P0 | Restart, duplicate-submission, lease/fencing and unknown-outcome tests |
| FR-AGENT-05 | EL_AGENT SHOULD provide local provider routing, offline model/voice support and explicit remote-provider consent | EL_AGENT | P1 | Provider contract tests; offline and consented remote tests |
| FR-AGENT-06 | EL_AGENT MAY integrate with HUB for paired identity, scoped task relay and status synchronization without making the integration mandatory | EL_AGENT + HUB | P1 | Pair/revoke/expiry/contract tests plus standalone-with-HUB-disabled test |
| FR-AGENT-07 | EL_AGENT MUST require explicit confirmation for sensitive or externally visible device actions | EL_AGENT | P0 | Confirmation bypass and stale approval tests |
| FR-WEB-01 | MR_SIAVASH_AI MUST provide public digital identity, portfolio, navigation and a responsive Persian/RTL experience | Website | P0 | Browser journeys, viewport matrix, accessibility checks |
| FR-WEB-02 | MR_SIAVASH_AI MUST present truthful implementation and release status, distinguishing public metadata from private runtime health | Website | P0 | Snapshot schema and UI contract tests; no private service inference |
| FR-WEB-03 | The public Gateway MUST expose only approved public knowledge/services and send only explicitly disclosed request data | Website | P0 | Data minimization, prompt-boundary and public/private isolation tests |
| FR-WEB-04 | Learning/workspace modules MUST preserve browser-local data boundaries and provide explicit export/recovery behavior where supported | Website | P1 | Storage migration, corruption and recovery tests |
| FR-WEB-05 | Publishing, support, admin and analytics functions MUST apply explicit consent, authentication, authorization and retention rules | Website | P1 | Auth, consent, retention, audit and deletion tests |
| FR-WEB-06 | Public modules and tools MUST declare their operational state and avoid presenting prototypes as production services | Website | P0 | Content/registry validation and UX acceptance |
| FR-X-01 | Cross-product calls MUST use versioned, authenticated, least-privilege contracts and stable service identities | Shared / HUB | P0 | Producer/consumer contract CI, unsupported-version tests |
| FR-X-02 | Cross-product data exchange MUST preserve owning-service authority; direct shared database access is prohibited | All | P0 | Architecture fitness tests and repository dependency scan |
| FR-X-03 | Cross-product operations SHOULD carry request/trace IDs, idempotency where applicable and bounded error envelopes | All | P1 | Contract tests and trace propagation tests |
| FR-X-04 | Integrations MUST support disable/revoke, expiry and graceful failure without weakening local product behavior | All | P0 | Revocation, timeout and offline-mode tests |

## 3. Non-functional requirements

| ID | Area | Requirement | Verification |
|---|---|---|---|
| NFR-SEC-01 | Security | Deny by default; least privilege; validated actor, scope and resource ownership | Negative authorization suites |
| NFR-SEC-02 | Secrets | No tokens, keys, pairing secrets or sensitive payloads in source, logs, browser storage or public errors | Secret scanning, log fixtures and code review |
| NFR-SEC-03 | AI safety | Model/tool output is untrusted; deterministic validators authorize actions | Prompt-injection and tool-boundary tests |
| NFR-PRIV-01 | Privacy | Public, private, device-local, customer and channel data are separated by explicit classification and consent | Data-flow review and cross-actor tests |
| NFR-REL-01 | Reliability | Bounded retries, explicit unknown outcomes, idempotency, cancellation and recovery where applicable | Fault injection and restart tests |
| NFR-OBS-01 | Observability | Structured logs/metrics/traces expose service health and execution outcomes without sensitive payload leakage | Instrumentation and redaction tests |
| NFR-COST-01 | Cost | Remote providers and paid infrastructure are opt-in, budgeted and visible | Configuration tests and cost evidence |
| NFR-PORT-01 | Portability | Models, providers, channels, stores and device adapters remain replaceable behind contracts | Architecture fitness and contract tests |
| NFR-PERF-01 | Performance | Payload, concurrency, timeout, context and resource budgets are explicit per service/action | Load/bounds tests; targets set after baseline |
| NFR-ACC-01 | Accessibility | Public web journeys support keyboard use, semantic structure, accessible contrast and responsive layouts | Automated and manual accessibility checks |
| NFR-I18N-01 | Localization | Persian/RTL is first-class where applicable, with safe mixed-script handling | Locale/RTL browser and text tests |
| NFR-MAINT-01 | Maintainability | Reproducible dependency management, documented contracts, focused modules and traceable ADRs | Dependency/CI audits and architecture review |
| NFR-REC-01 | Recovery | Backups, restore, rollback and recovery procedures are documented and rehearsed where data or release impact warrants | Restore/rollback rehearsal evidence |

## 4. Cross-cutting acceptance matrix

| Concern | Mandatory negative case | Owning phase(s) |
|---|---|---|
| Identity | Unknown, expired, revoked or mismatched actor is denied | H11, E1, E13, D2, A6/A8, X2 |
| Scope | Caller requests capability beyond granted scope | H11, H6, E5/E6/E11/E12, D3/D11 |
| Public/private | Private owner prompt/result/memory is never sent to Website public Gateway or public actor | E2/E13, A5/A6, X2/X8 |
| Idempotency | Duplicate request/update does not duplicate non-idempotent effect | H1/H8, E10, D4, X9 |
| Unknown outcome | Network timeout after a side effect is not reported as confirmed success and is not blindly replayed | H8, E10, D4 |
| Bounds | Oversize payload, long timeout, excessive retries or resource exhaustion is rejected safely | All execution adapters |
| Revocation | Revoked grant or disconnected adapter cannot continue using stale authority | H11, E1/E13, D11, X2 |
| Evidence | Missing, stale, conflicting or untrusted evidence cannot produce accepted completion | H10, E8, D14, X7 |
| Offline | Local core remains usable when HUB/cloud unavailable | D0–D14 |
| Release | Failed candidate can be rolled back without affecting unrelated product data | H19, E14, D14, A14 |

## 5. Traceability workflow

The initial requirement-to-phase/use-case map is maintained in [REQUIREMENT_USECASE_TRACEABILITY.md](../traceability/REQUIREMENT_USECASE_TRACEABILITY.md). It is an index only; it does not mark implementation or acceptance complete.

Each requirement is decomposed into a Work Order with:
- requirement ID(s);
- owning product and accountable owner;
- linked technical phase and predecessor gates;
- source paths and exact commit baseline;
- implementation and test changes;
- expected success, denial and recovery cases;
- acceptance evidence and residual risk;
- release impact and rollback path.

A requirement is not closed because prose exists. Closure requires a passing test/evidence link or a recorded owner decision for a non-automatable gate.
