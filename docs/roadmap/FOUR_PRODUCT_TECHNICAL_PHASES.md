# Four-Product Technical Phase Inventory

- **Baseline date:** 2026-11-27
- **Status:** Active planning baseline; phase acceptance is evidence-driven and must be refreshed from exact mainline heads.
- **Governance prerequisite:** [G0–G12](../GOVERNANCE_PRODUCT_STRATEGY_G0_G12.md)
- **Portfolio authority:** [ADR-0051](../architecture/decisions/ADR-0051-four-product-ecosystem-scope-and-telegram-ownership.md)
- **Requirement catalogue:** [G2 requirements](../requirements/ECOSYSTEM_REQUIREMENTS.md)
- **Use cases:** [G3 use-case catalogue](../architecture/USE_CASE_CATALOG.md)
- **Ownership:** [G5 RACI](../governance/OWNERSHIP_RACI.md)

## 1. Scope and phase accounting

The active technical portfolio contains 76 phases across four products and shared contracts:

| Workstream | IDs | Count | Owner |
|---|---|---:|---|
| Central intelligence | H0–H20 | 21 | MR_SIAVASH_HUB_AI |
| Personal agent / Telegram bot | E0–E14 | 15 | MR_SIAVASH_EL_AI |
| Local/device runtime | D0–D14 | 15 | MR_SIAVASH_EL_AGENT |
| Public platform / workspace | A0–A14 | 15 | MR_SIAVASH_AI |
| Shared integration/security/infrastructure contracts | X1–X10 | 10 | HUB coordinates; all consumers own compatibility |

G0–G12 are portfolio governance phases and are tracked separately; they are not included in the 76 technical phase count.

**No B0–B11 stream exists in the active portfolio.** The ecosystem Telegram bot belongs to EL_AI and is covered by E10. `MR_SIAVASH_EL_IR_BOT` is outside scope. Historical phase evidence from the former B stream is not transferred to EL_AI.

## 2. Status vocabulary and rules

- **Evidence exists — acceptance pending:** source/docs/tests are present, but phase-level criteria have not been reconciled.
- **Partial:** only part of the capability or its acceptance evidence exists.
- **Planned:** no sufficient implementation evidence was established in the current read.
- **Owner/environment gate:** code/CI cannot complete the phase without a separately authorized live environment, account or physical device.
- **Done:** all phase-specific criteria, dependencies and exact-mainline verification are satisfied.

At this baseline no phase is globally declared DONE by this inventory. The repository contains substantial implementation; phase completion must be audited at the exact owning main SHA.

## 3. HUB — H0 through H20

| Phase | Scope / deliverable | Main dependencies | Current evidence posture | Minimum exit gate |
|---|---|---|---|---|
| H0 | Repository, configuration, architecture, test and trust-boundary foundation | — | Evidence exists | Reproducible clean setup, architecture map, safe defaults and baseline checks |
| H1 | Durable workflow definitions, DAG validation, stable step identity and state transitions | H0, X1 | Evidence exists | Invalid DAG, duplicate step, concurrent transition and restart tests |
| H2 | AWI planning, task decomposition, dependency graph and plan revision | H1, X1 | Evidence exists | Deterministic constraints, bounded plans, revision and dependency tests |
| H3 | GPI intent/context, WorkOrder schema, acceptance and verification plan | H2, H12 | Evidence exists | Schema and endpoint tests for incomplete, ambiguous and adversarial inputs |
| H4 | CGI capability-gap discovery, assessment, matching and evaluation | H3, H6, H11 | Evidence exists | Missing/stale/untrusted capability cases produce explicit gaps, never fabricated capability |
| H5 | Risk-aware strategy and decisions: model/tool/path selection and revision | H3, H4, H6, H14 | Partial | Deterministic risk/policy gates and measurable strategy evaluation |
| H6 | Versioned tool/skill manifests, validation, registry and lifecycle | H11, X1 | Evidence exists | Permission, schema, version, lifecycle and revocation tests |
| H7 | Worker execution, step dispatch, context and resource budgets | H1, H11, H12, H16 | Evidence exists | Bounded execution, isolation, cancellation and trusted results |
| H8 | Retry, idempotency, checkpoints, recovery and unknown-outcome handling | H7, H11, H16 | Evidence exists | Fault-injection and crash/restart tests; no unsafe replay |
| H9 | Private memory, knowledge, retrieval, provenance and selective sharing | H11, H16, X3 | Evidence exists | Owner isolation, export/delete, provenance and retrieval-quality acceptance |
| H10 | Evidence evaluator, completion, correction, replanning and lessons | H7, H8, H9, H12 | Partial — evaluator contract tests merged; owner-scoped API candidate in PR #641 | Merge/API acceptance, canonical WorkOrder digest/revision persistence, production verifier adapters, E8 consumer integration and negative evidence matrix |
| H11 | Identity, authentication, authorization, policy, approvals, grants and audit | H0, X1, X2 | Evidence exists | Negative auth, expiry, revocation, replay and audit tests |
| H12 | Versioned APIs, contract validation, errors, rate limits and compatibility | H7, H8, H11, X1 | Evidence exists | OpenAPI/schema validation and consumer compatibility across supported versions |
| H13 | Specialist agents, delegation, handoff, aggregation and conflict handling | H3, H4, H7, H8, H11, H14 | Partial | Delegation remains budgeted, bounded, attributable and measurably useful |
| H14 | Model/provider registry, capability routing, local/cloud policy and context budgets | H6, H11, X6 | Evidence exists | Provider substitution tests, explicit routing and no hidden cloud fallback |
| H15 | Logs, metrics, traces, health/readiness, alerts and execution analytics | H0, X7 | Evidence exists | Correlation across API/worker/task, redaction, health semantics and alert tests |
| H16 | Data schemas, migrations, transactions, integrity, retention and backups | H0, X1 | Evidence exists | Additive migration tests, integrity checks and restore/recovery drill |
| H17 | Operator/control center for tasks, agents, tools, memory, policy and operations | H12, H13, H15 | Partial | Authorized workflows and UI/API contract tests; no hidden admin access |
| H18 | Async performance, quotas, concurrency and load management | H7, H8, H15 | Partial | Representative load baseline, queue saturation and fairness tests |
| H19 | Quality, security, regression, E2E, CI/CD and release governance | Critical H phases | Evidence exists | Exact-head CI, protected main, release/rollback evidence and security review |
| H20 | Research, adaptive planning, simulation and bounded self-improvement | H19 | Planned / gated | Benchmark benefit, sandbox, owner approval, rollback and no self-acceptance |

## 4. EL_AI — E0 through E14

EL_AI owns the complete Telegram implementation boundary, including adapters/workers where needed. It does not depend on a separate Telegram Bridge repository.

| Phase | Scope / deliverable | Main dependencies | Current evidence posture | Minimum exit gate |
|---|---|---|---|---|
| E0 | Application/runtime foundation, configuration, lifecycle and test harness | H0, X1 | Evidence exists | Clean install, deterministic startup/shutdown, config validation and CI |
| E1 | Owner identity, pairing, credential storage and personalization | E0, H11, X2 | Evidence exists | Pair/expire/revoke/scope isolation and secure secret storage tests |
| E2 | Conversation/session context and actor separation | E0, E1 | Evidence exists | Public/private isolation, context minimization and persistence semantics |
| E3 | Intent interpretation and command routing aligned to GPI | E2, H3 | Evidence exists | Ambiguous/unsupported intent, command allowlist and prompt-injection tests |
| E4 | Dependency-aware planning and safe task-plan previews | E3, H2 | Evidence exists | Preview does not execute; dependent steps unlock only after verified prerequisites |
| E5 | Durable task submission and result consumption through HUB | E4, H7, H8, H11, H12 | Evidence exists | Idempotency, scope, retry, cancellation and owner-isolation contract tests |
| E6 | Approved capability/tool discovery and routing | E5, H6, H11, X5 | Partial | Every tool is manifest-bound, scope-checked, budgeted and audited |
| E7 | Owner-scoped memory access and learning flows | E1, H9, X3 | Evidence exists | Memory scopes, provenance, export/delete and no public-context leakage |
| E8 | Evidence review, user-visible correction and plan replanning | E5, E7, H10 | Partial | Terminal state is not semantic acceptance; full evidence-negative matrix |
| E9 | Model/provider choice and routing under HUB policy | E0, H14, X6 | Partial | Provider substitution, consent, secret handling, budget and local/cloud routing tests |
| E10 | Dedicated Telegram bot: update intake, polling/webhook adapters, command lifecycle, send/delivery state, idempotency, retry/rate-limit handling and media | E0, E1, E2, E3, E13 | Partial — Unicode validation slice merged in PR #148 (`bb7239c4`); Python 3.11/3.12 and post-merge security/supply-chain checks passed | Full Telegram adapter state-machine coverage, test-bot configuration and real E2E acceptance; duplicate/unknown/expired/rate-limit/media paths and operational runbook |
| E11 | Optional EL_AGENT client/command bridge for owner-authorized device capabilities | E1, E5, D11, X2, X9 | Planned / gated | Versioned typed contract, explicit grants, confirmation, cancellation, revocation and device evidence |
| E12 | Bounded autonomous plans/chains, budgets, pause/resume and kill switch | E5, E8, H7, H8, H11 | Evidence exists — acceptance pending | All continuation points revalidate owner pause, grants, budget and deadlines |
| E13 | EL_AI security/privacy, actor contexts, audit and prompt/context protection | E0, H11, X8 | Evidence exists | Independent threat review and negative tests for owner/public/customer contexts |
| E14 | Cross-product integration, release, operations and end-to-end acceptance | E5–E13, H19, X1–X10 | Partial / owner gate | Real Telegram acceptance, deployment/runbook, backup/incident plan and exact-release verification |

## 5. EL_AGENT — D0 through D14

EL_AGENT owns device execution and remains useful as a standalone local product. HUB pairing is optional.

| Phase | Scope / deliverable | Main dependencies | Current evidence posture | Minimum exit gate |
|---|---|---|---|---|
| D0 | Repository, packaging, configuration, platform support and safe defaults | — | Evidence exists | Reproducible Windows/Android build/install and support matrix |
| D1 | Local runtime/API/CLI/desktop foundation | D0 | Evidence exists | Loopback-only/API auth, lifecycle and invalid-request tests |
| D2 | Local identity, credential storage and session protection | D1 | Evidence exists — local API token file hardening merged in PR #33 (`de8007bd`); Linux/Windows Python 3.11/3.12 tests passed | Android Keystore-backed credential acceptance, session lock/revoke, physical-device tamper/expiry and clean Windows installation evidence |
| D3 | Typed capability manifests and deterministic local policy engine | D1, D2 | Partial | Default deny; schema, scope, confirmation and bounds tests for all actions |
| D4 | Local scheduler, idempotency, leases, recovery and cancellation | D1, D3 | Evidence exists | Restart/duplicate/stale lease/unknown outcome and safe recovery tests |
| D5 | Local and remote provider abstraction, model routing and offline fallback | D0, D3 | Evidence exists | Local-only test with network blocked; remote use only after explicit consent |
| D6 | On-device planning, structured proposals and bounded task decomposition | D3, D5 | Partial | Malformed/adversarial model output rejected by deterministic policy |
| D7 | Windows tools, app intents, desktop control center and local automation | D1, D3, D4 | Evidence exists | Real Windows 11 install, restart/offline, microphone and control-surface acceptance |
| D8 | Android companion, foreground task consumer, storage picker and platform adapters | D0, D2, D3 | Evidence exists | Physical-device acceptance across supported Android versions and permission denial paths |
| D9 | Voice pipeline: push-to-talk, local STT/TTS, optional cloud STT with consent | D5, D7, D8 | Partial | Offline behavior, explicit microphone state, no ambient upload, physical mic/audio acceptance |
| D10 | Device-local preferences/memory, provenance, retention, export and deletion | D1, D2, D3 | Partial / planned | Local data isolation, user controls and secure export/delete tests |
| D11 | Optional HUB pairing, device registry/heartbeat and scoped task consumer | D2, D3, X1, X2, X9 | Partial | HUB unavailable/offline independence, pairing/revoke/expiry and real staging round-trip |
| D12 | Desktop UX and Android owner-review experience | D7, D8, D9 | Partial | Accessibility, responsive/device acceptance and clear action confirmation/results |
| D13 | Device security, audit, observability, update integrity and incident/recovery | D2–D12, X7, X8 | Partial | Independent security review, redaction, update integrity and recovery/rollback evidence |
| D14 | Packaging, release, compatibility and physical-device acceptance | D0–D13, H19 | Owner/environment gate | Signed/reproducible package, Windows and Android acceptance matrix, rollback and support runbook |

## 6. MR_SIAVASH_AI — A0 through A14

| Phase | Scope / deliverable | Main dependencies | Current evidence posture | Minimum exit gate |
|---|---|---|---|---|
| A0 | Static-site foundation, build, routing, hosting boundaries | — | Evidence exists | Reproducible build, security headers and deployment/source provenance |
| A1 | Digital identity, public information architecture and navigation | A0 | Evidence exists | User journey and content accuracy review |
| A2 | Responsive design, accessibility, typography, themes and motion | A0, A1 | Evidence exists | Keyboard, screen-reader, contrast, viewport and RTL acceptance |
| A3 | Portfolio, project catalogue and truthful status metadata | A0, A1 | Evidence exists | Public-only fields, staleness labels and no private runtime inference |
| A4 | Learning/knowledge center and content curriculum | A0, A2 | Evidence exists | Content QA, navigation and browser-local progress tests |
| A5 | Public assistant UX, session/privacy disclosure and content workflow | A0–A2 | Evidence exists | Disclosure/consent, response bounds and public/private isolation |
| A6 | Secure public Gateway, validation, quotas, rate limits and service protection | A5, H11 | Evidence exists | Threat model, abuse controls, secret isolation and exact-candidate runtime smoke |
| A7 | Optional private HUB integration only through versioned authenticated contracts | A6, H11, H12, X1, X2 | Proposed / not enabled | Separate owner-approved product decision, public/private data-flow proof and negative auth tests |
| A8 | Access-protected administration and append-only audit | A6, H11, H12, H15 | Evidence exists | Identity/access JWT checks, role separation and audit tests |
| A9 | Content authoring, editorial workflow and publishing controls | A5, A8 | Evidence exists | Draft/review/approval and publication rollback tests |
| A10 | Public AI/developer tools with bounded local/browser execution | A6, H6 | Evidence exists | No arbitrary remote execution; content/data limits and safe offline behavior |
| A11 | Explicit public integrations (GitHub, Telegram links, APIs) | A6, X1, X2 | Partial | Scope, consent, credential, failure and revocation tests |
| A12 | Consent-based analytics/support, minimization, retention and CRM | A6, A8, H11 | Partial | Remote migration/release, retention execution and privacy acceptance where applicable |
| A13 | Security, performance, SEO, caching, accessibility and payload hardening | A0–A12 | Partial | Exact-main browser/asset/security budgets and regression review |
| A14 | Production readiness, monitoring, backup, rollback and release | A13, H19 | Owner/environment gate | Fresh live control-plane readback, migration/backup evidence, deployment provenance and owner release decision |

## 7. Shared integration — X1 through X10

| Phase | Scope / deliverable | Main dependencies | Minimum exit gate |
|---|---|---|---|
| X1 | Versioned contracts: ActorContext, WorkOrder, Task, ToolCall, AttachmentRef, ArtifactRef, ExecutionResult, Error and events | H0, E0, D0, A0 | Schemas validate in every producer/consumer; unsupported versions fail explicitly |
| X2 | Service identity, owner pairing, scopes, leases, expiry and revocation | X1, H11, E1, D2 | Cross-product identity and negative authorization matrix |
| X3 | Permissioned shared memory/knowledge interface with provenance | X1, X2, H9 | Only explicit owner-approved data is shared; export/delete and access audit |
| X4 | Agent/device/capability registry with lifecycle and trust metadata | X1, H13, D11 | Registration, capability/version checks, stale device and revoke behavior |
| X5 | Tool/skill manifests and capability contracts | X1, H6, E6, D3 | Producer/consumer compatibility and permission lifecycle tests |
| X6 | Model/provider identity, capabilities, routing and budget contracts | X1, H14, E9, D5 | Provider substitution, cost/consent and no-fallback tests |
| X7 | Correlation, tracing, logs, metrics and health vocabulary | X1, H15 | Cross-product trace continuity without secrets/payload leakage |
| X8 | Security baseline: threat models, policy, secrets, audit, AI safety and data classification | H11, X1, X2 | Independent threat review and cross-product negative security suite |
| X9 | Cross-product workflow and typed event/task relay | X1, X2, X4, X5, H7, E5, E11, D11 | Idempotency, expiry, cancellation, failure isolation and compatibility tests |
| X10 | Ecosystem control/visibility and release metadata | X2, X4, X7, X9, H12, H15, H17 | Evidence freshness, capability state, health boundaries and role-gated operations |

## 8. Critical dependency order

1. **Governance:** G0–G8 define why, what, who, interfaces and controls.
2. **Foundations:** H0/H11/H12/H16, E0/E1/E2/E13, D0/D1/D2/D3, A0/A1/A2, X1/X2/X8.
3. **Core value paths:** HUB planning/worker/evaluator; EL_AI conversation/Telegram; EL_AGENT offline execution; Website public experience/Gateway.
4. **Integration:** X3–X7, then X9 and X10; EL_AI E11 and EL_AGENT D11 remain optional, scoped integrations.
5. **Release:** H19, E14, D14, A14; never treat CI as live/device/production acceptance.

Parallel implementation is allowed where contract versions are stable and ownership does not overlap. Integration and release remain dependency ordered.

## 9. Global phase Definition of Done

A phase may be marked DONE only when:
- requirements and acceptance criteria are traceable;
- owning implementation exists in the correct repository;
- negative, failure, recovery, authorization and bounds tests relevant to the phase pass;
- dependent consumers use the documented versioned contract;
- security and privacy gates pass, with independent review when required;
- exact-head CI passes before merge and current mainline checks pass after merge;
- live runtime/device/database/production acceptance is recorded separately where applicable;
- rollback, operational owner and residual risks are documented.

A code branch, PR, green CI, historical checklist or proposed architecture alone cannot close a phase.

## 10. Initial priority queue

1. Merge and apply ADR-0051 and the G0–G12 governance artifacts.
2. Finish G2/G3 traceability and G5 ownership review.
3. Reconcile each product's mainline implementation against H/E/D/A/X phase acceptance criteria.
4. Prioritize H10 evidence-verification gaps, EL_AI E10 Telegram runtime/delivery acceptance, EL_AGENT D3/D7–D14 local/device acceptance and Website A12–A14 release gates.
5. Publish contract fixtures and run producer/consumer CI before enabling optional cross-product execution.
6. Address branch protection for all four repositories through owner/admin configuration and independent verification.
7. Begin the next phase only when its own dependency gates and source ownership are clear.


## 11. Exact implementation evidence links — 2026-11-27

| Phase / requirement slice | Owning repository | Exact merged source / tests | Evidence state | Not covered by this slice |
|---|---|---|---|---|
| D2 local token-file security (subset of FR-AGENT-02/NFR-SEC-02) | EL_AGENT | PR #33 merge `de8007bd3a32e636a589d8afb7806725ac55d414`; `src/el_agent/security.py`, `tests/test_security.py` | Exact PR-head Python 3.11/3.12 Linux+Windows matrix passed; post-merge exact-main matrix passed on the recorded SHA | Android Keystore, physical device, system-level session lock/revoke and full device identity acceptance |
| E10 outbound Unicode validation (subset of FR-ELAI-02/05) | EL_AI | PR #148 merge `bb7239c46556f6fa68841e48740507f31ba58e6c`; `src/el_ai/telegram/api.py`, `tests/test_telegram_api.py` | Python 3.11/3.12, Workflow Security Audit, post-merge Security Audit and Scorecard passed | Full update intake and delivery state machine, live test-bot, webhook and unknown-outcome E2E |
| H10 evaluator regression contract (FR-HUB-06) | HUB | PR #640 merge `47a8e4fee206ef72e928fa3ce381a52ee4324921`; `tests/test_work_order_evidence_contract.py` | Exact PR-head validation checks passed before merge | Owner-scoped API and trusted production evidence adapters |
| H10 owner-scoped evaluation API (FR-HUB-06) | HUB | PR #641 current candidate; `backend/mrhub/api/routes/agent.py`, `backend/mrhub/agents/work_order_evidence.py`, `tests/test_agent_work_order_evidence_api.py` | Open PR; CI pending at this snapshot; candidate rechecks encrypted plan digest and binds a separate canonical WorkOrder digest | Production verifiers, persisted WorkOrder revision/digest, E8 consumer integration and exact-main acceptance |

## 11. Merged implementation slices and open acceptance — 2026-11-27

This table records narrow implementation slices; it does not promote the owning phase to DONE.

| Phase | Exact merged source | Test/CI evidence observed | Remaining phase acceptance |
|---|---|---|---|
| D2 | EL_AGENT PR #33, merge `de8007bd3a32e636a589d8afb7806725ac55d414`; `src/el_agent/security.py`, `tests/test_security.py` | Exact PR-head Linux/Windows × Python 3.11/3.12 passed; post-merge main checks passed on that source snapshot | Android Keystore and physical Windows/Android credential lifecycle acceptance |
| E10 | EL_AI PR #148, merge `bb7239c46556f6fa68841e48740507f31ba58e6c`; `src/el_ai/telegram/api.py`, `tests/test_telegram_api.py` | Python 3.11/3.12, Workflow Security Audit and post-merge Scorecard/security checks passed | Real test-bot E2E, update intake, delivery state reconciliation, duplicate/retry/rate-limit/media/unknown-outcome acceptance |
| H10 | HUB PR #640, merge `47a8e4fee206ef72e928fa3ce381a52ee4324921`; `tests/test_work_order_evidence_contract.py` | Exact PR-head validation suite passed before merge; post-merge main test matrix was in progress at latest read | PR #641 owner-scoped API candidate, separate canonical WorkOrder revision/digest persistence, trusted production verifier adapters, E8 consumer contract and exact-main validation |
| G0–G12 | HUB PR #639 — open, not yet merged | Python 3.11/3.12 and final CI checks still running at latest read | Review ADR-0051, resolve one-commit main divergence, complete exact-head CI and merge; owner/legal/admin gates remain |

