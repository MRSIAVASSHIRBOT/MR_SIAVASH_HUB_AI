# MR_SIAVASH Ecosystem — 73-Phase Baseline

**Baseline date:** 2026-11-23  
**Purpose:** Establish a traceable planning contract for the 73-phase roadmap.  
**Status semantics:** This file is a dependency and evidence baseline. It does **not** declare any phase complete.

## 1. Scope and source-of-truth boundary

The requested execution scope currently names these repositories:

| Requested role | Repository | Ownership boundary |
|---|---|---|
| Hub | `MRSIAVASSHIRBOT/MR_SIAVASH_HUB_AI` | Authoritative planning, policy, task/workflow execution, persistence, tools, memory and audit |
| Conversational agent | `MRSIAVASSHIRBOT/MR_SIAVASH_EL_AI` | Conversation, Telegram-facing user experience, owner identity mapping and scoped Hub client |
| Public website | `MRSIAVASSHIRBOT/MR_SIAVASH_AI` | Public site, public Gateway, learning/content UX and public integrations |
| Telegram bridge | `MRSIAVASSHIRBOT/MR_SIAVASH_EL_IR_BOT` | Telegram transport bridge, durable delivery queue, idempotency and delivery recovery |

**Scope discrepancy requiring an explicit architecture decision:** the Hub's canonical ecosystem document, `docs/PROJECT_GOALS_ECOSYSTEM.md`, identifies `MR_SIAVASH_EL_AGENT` (Windows/Android companion) as the fourth product, not `EL_IR_BOT`. The EL_AI coordinated checkpoint also includes EL_AGENT. The four repositories named in this baseline therefore represent the requested execution set, not yet a reconciled canonical product taxonomy. Do not silently drop EL_AGENT or silently reclassify EL_IR_BOT. Record the chosen product boundary and ownership in an ADR before implementing cross-project contracts that depend on it.

The roadmap text in the originating request contains a placeholder for a Persian reference rather than the Persian text itself. This baseline is therefore aligned to the supplied English phase list and the checked-in repository evidence available on 2026-11-23.

### Repository snapshot used to start this baseline

| Repository | Observed `main` SHA | Open PRs observed | Mainline workflow observation |
|---|---|---:|---|
| Hub | `131785f504dd4401c5be2bf987090b7962a6d77c` | #605, #607 | Recent mainline CI groups succeeded |
| EL_AI | `732b970c333e9bdba1227efc04eb96c86b064780` | None | Recent mainline CI/security checks succeeded |
| Website | `9ab2a33d5022188e7f635a7f796177717e6b774f` | None | Recent mainline quality, Gateway and security checks succeeded |
| EL_IR_BOT | `b3b64d4a5221d741e2bdd365b1d194d4449f8522` | None | Recent mainline tests and security checks succeeded |

This is a dated GitHub source/CI snapshot, not a deployment claim. The observed `main` branches in all four repositories were unprotected. PR CI, production deployment, Telegram acceptance, physical-device acceptance, remote database migrations and live-provider acceptance must be reported separately.

The current Hub PR queue is tracked directly in GitHub:
- [PR #605 — H4 action-bound approval receipts](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_HUB_AI/pull/605). Open; exact-head CI was being repaired at baseline time. Do not merge until all exact-head checks and security regressions pass.
- [PR #607 — Render runtime separation](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_HUB_AI/pull/607). Draft; source/CI work does not provision services. Workspace Blueprint Auto Sync, service pricing, persistent-disk charges, secrets and rollback require separate review before any account sync or provisioning.

## 2. Phase inventory and minimum dependency gates

The dependency column describes minimum integration gates, not a requirement that all implementation work be strictly serial. Parallel development is allowed behind stable contracts; integration and release remain dependency-ordered.

### Hub — H0 through H20

| Phase | Owner | Capability boundary | Minimum dependency gates |
|---|---|---|---|
| `H0` | Hub | Repository integrity, architecture baseline, configuration, build/test conventions and trust boundaries | — |
| `H1` | Hub | Workflow definition, DAG validation, stable step identity, state transitions and checkpoints | H0 |
| `H2` | Hub | AWI goal decomposition, task graph construction, dependency planning, validation and revision | H1, X1 |
| `H3` | Hub | GPI intent/context understanding, WorkOrder, constraints, acceptance criteria and verification plan | H2, H12 |
| `H4` | Hub | Capability registry, assessment, gap detection, matching and capability evaluation | H3, H6, H11 |
| `H5` | Hub | Risk-aware strategy, tool/model/path selection, scoring and decision revision | H3, H4, H6, H14 |
| `H6` | Hub | Tool/skill manifests, discovery, schemas, validation, routing and lifecycle | H11, X1 |
| `H7` | Hub | Execution queue, context, step dispatch, concurrency limits, results and resource budgets | H1, H11, H16, X1 |
| `H8` | Hub | Retry/backoff, checkpoint recovery, resume, idempotency, failure isolation and unknown outcomes | H7, H11, H16 |
| `H9` | Hub | Working, episodic, semantic and procedural memory; retrieval, scoring, consolidation and scoped sharing | H11, H16, X3 |
| `H10` | Hub | Evidence evaluation, goal completion, quality scoring, correction, replanning and lessons | H7, H8, H9, H12 |
| `H11` | Hub | Authentication, authorization, policy, risk classification, tool grants, secrets, audit and isolation | H0, X1 |
| `H12` | Hub | Versioned API/service contracts, validation, error envelope, rate limits and service boundaries | H7, H8, H11, H16, X1 |
| `H13` | Hub | Multi-agent registry, delegation, handoff, communication, aggregation and conflict handling | H3, H4, H7, H8, H11, H14 |
| `H14` | Hub | Model/provider registry, capability-aware routing, local/cloud policy, fallback and context budgets | H6, H11, X6 |
| `H15` | Hub | Structured logs, metrics, traces, health/readiness, heartbeat, alerts and execution analytics | H0, X7; instrumentation starts at H0 |
| `H16` | Hub | Database design, schema/migrations, transactions, integrity, retention, backup and versioning | H0, X1 |
| `H17` | Hub | Admin/control center for agents, tasks, workflows, tools, memory, policy and operations | H12, H13, H15 |
| `H18` | Hub | Async execution, queue performance, caching, concurrency, quotas and load management | H7, H8, H15 |
| `H19` | Hub | Continuous quality gates, security/regression/E2E, CI/CD, release governance and docs | All critical Hub phases; quality checks start at H0 |
| `H20` | Hub | Advanced research, adaptive planning, simulation and bounded self-improvement experiments | H19 and explicit safety/resource/rollback gates |

### EL_AI — E0 through E14

| Phase | Owner | Capability boundary | Minimum dependency gates |
|---|---|---|---|
| `E0` | EL_AI | Agent runtime foundation, configuration, local lifecycle and test harness | H0, X1 |
| `E1` | EL_AI | Identity, owner pairing and personalization | E0, X2, H11 |
| `E2` | EL_AI | Conversational state, context boundaries and user interaction | E0, E1 |
| `E3` | EL_AI | Goal/intent understanding aligned to Hub GPI | E2, H3 |
| `E4` | EL_AI | Planning and task decomposition aligned to Hub AWI | E3, H2 |
| `E5` | EL_AI | Bounded task/agent execution through Hub contracts | E4, H7, H8, H11, H12 |
| `E6` | EL_AI | Tool/skill discovery and routing through approved registries | E5, H6, H11, X5 |
| `E7` | EL_AI | Owner-scoped memory and learning | E1, H9, X3 |
| `E8` | EL_AI | Evidence evaluation, correction and replanning | E5, E7, H10 |
| `E9` | EL_AI | Model selection/routing under Hub model and budget policy | E0, H14, X6 |
| `E10` | EL_AI | Telegram-facing interface and message delivery integration | E2, B7 |
| `E11` | EL_AI | Desktop/local agent with sandboxed, policy-gated, audited and reversible operations | E0, E13, H11 |
| `E12` | EL_AI | Bounded autonomous operations, chains, budgets, cancellation and kill switch | E5, E8, H7, H8, H11, H13 |
| `E13` | EL_AI | Agent security, permissions, trust boundaries, audit and context protection | E0, H11, X8 |
| `E14` | EL_AI | Cross-project integration, release, monitoring and end-to-end validation | E5, E6, E7, E8, E9, E10, E13, H19 |

### Public website — A0 through A14

| Phase | Owner | Capability boundary | Minimum dependency gates |
|---|---|---|---|
| `A0` | Website | Website foundation, build, routing and deployment boundaries | H0 |
| `A1` | Website | Digital identity, navigation and public information architecture | A0 |
| `A2` | Website | Responsive design system, accessibility, typography, motion and themes | A0 |
| `A3` | Website | Portfolio, project catalogue and truthful project status | A0, A1 |
| `A4` | Website | Learning/knowledge center and public learning content | A0, A2 |
| `A5` | Website | AI interface, sessions, streaming and editorial/content workflow | A0, A1, A2; public/private boundary enforced |
| `A6` | Website | Secure public AI Gateway, validation, quotas, rate limits and usage control | A5, H11 |
| `A7` | Website | Private Hub integration through versioned, authenticated contracts | A6, H11, H12, X1, X2 |
| `A8` | Website | Access-protected admin panel and append-only audit | A6, H11, H12, H15 |
| `A9` | Website | Content engine, articles, tutorials and publishing controls | A5, A8 |
| `A10` | Website | AI/developer tools with bounded public interfaces | A6, A7, H6 |
| `A11` | Website | Telegram/GitHub/AI API integrations with explicit scopes | A6, A7, X1, X2 |
| `A12` | Website | Analytics and CRM with minimization, consent and retention | A6, A8, H11 |
| `A13` | Website | Security, performance, SEO, caching and accessibility hardening | A0–A12 as applicable |
| `A14` | Website | Production readiness, release, monitoring, rollback and evolution | A13, H19 |

### EL_IR_BOT — B0 through B11

| Phase | Owner | Capability boundary | Minimum dependency gates |
|---|---|---|---|
| `B0` | EL_IR_BOT | Bridge foundation, configuration and trust boundaries | H0, X1 |
| `B1` | EL_IR_BOT | Telegram update receive/send transport | B0, B6 |
| `B2` | EL_IR_BOT | Delivery state machine, acknowledgement and duplicate prevention | B1, B5, B6 |
| `B3` | EL_IR_BOT | Durable job queue, lifecycle, priority and leases | B0, B5 |
| `B4` | EL_IR_BOT | Retry/backoff, quarantine and unknown-outcome recovery | B2, B3, B5 |
| `B5` | EL_IR_BOT | D1 persistence, schema, migrations and integrity | B0 |
| `B6` | EL_IR_BOT | Secret handling, identity, endpoint protection and authorization | B0, X2, X8 |
| `B7` | EL_IR_BOT | EL_AI Bridge integration for task/result delivery | B1, B2, B3, B4, B5, B6, E0, E1 |
| `B8` | EL_IR_BOT | Hub integration through scoped APIs and contracts | B7, H11, H12, X1, X2 |
| `B9` | EL_IR_BOT | Media/content transport and Telegram limits | B1, B2, B5, B6 |
| `B10` | EL_IR_BOT | Structured logs, metrics, health and delivery analytics | B0, B3, B5, X7 |
| `B11` | EL_IR_BOT | Tests, CI, performance, security, deployment and release | B2, B4, B5, B6, B7, B8, B9, B10 |

### Shared integration — X1 through X10

| Phase | Owner | Capability boundary | Minimum dependency gates |
|---|---|---|---|
| `X1` | Shared contracts | Versioned API, Task, Agent, Message, Memory and Error contracts | H0, H1; define early and freeze before cross-project integration |
| `X2` | Shared identity | Shared identity, pairing, scoped authorization and revocation | X1, H11, E1 |
| `X3` | Shared memory | Permissioned, owner-scoped memory interfaces and provenance | X1, X2, H9 |
| `X4` | Shared agent registry | Agent identity, capabilities, lifecycle and trust metadata | X1, H13 |
| `X5` | Shared tool registry | Tool/skill schema, versioning, permission and lifecycle contracts | X1, H6, H11 |
| `X6` | Shared model infrastructure | Model/provider identity, capability and budget contracts | X1, H14 |
| `X7` | Shared observability | Correlation IDs, log/metric/trace conventions and health vocabulary | X1, H15 |
| `X8` | Shared security | Cross-service policy, secrets, trust boundaries and audit | H11, X1, X2 |
| `X9` | Cross-project workflows | Authenticated workflows that cross service boundaries | X1, X2, X4, X5, H7, H12, E5, B7 |
| `X10` | Unified control plane | Unified visibility/control for agents, tasks, projects and services | X2, X4, X7, X9, H12, H13, H15, H17 |

## 3. Parallelization policy

The following work can proceed in parallel when branches consume the same published contract version:

1. **Foundation:** H0/H1 and the first X1 contract draft. H2 planning design can proceed while X1 is being finalized, but cross-service implementation must use a frozen contract version.
2. **Hub foundation services:** H11 and H16 can be built concurrently. H7 can develop against their interfaces; executable integration is gated on authorization and persistence. H8 follows H7's durable state model; H12 follows the H7/H8/H11/H16 contract.
3. **Hub intelligence:** H3/H4/H6/H9/H14 can overlap after the required task, tool, memory and model interfaces are stable. H5 and H10 depend on their upstream evidence and cannot be treated as independent islands.
4. **EL_AI:** E0/E1/E2 can overlap. E3/E4/E5/E6/E7/E8/E9 can proceed as contract-backed slices. E11 remains independently sandboxed; E12 is gated on execution, recovery, security and cancellation.
5. **Website:** A0/A1/A2/A3/A4/A5/A6 can proceed largely independently within the public boundary. A7 must wait for private service contracts and X2. A8/A9/A10/A11/A12 can overlap once their identity, privacy and public/private boundaries are clear.
6. **Bridge:** B0/B1/B5/B6/B10 can overlap. B2/B3 depend on persistence and delivery-state contracts; B4 follows; B7/B8 follow the EL_AI and Hub integration contracts. B9 can proceed once transport and media limits are explicit.
7. **Shared services:** X2/X8 are early trust foundations. X3/X4/X5/X6/X7 should be defined alongside their owning modules. X9 and X10 are late integration layers, not prerequisites for the first vertical slice.
8. **Cross-cutting:** H15 observability and H19 quality gates begin in H0. They are not postponed until the scale/release tiers.

Parallelism never permits a shared database, implicit trust, public-to-private context forwarding, unbounded delegation, unbounded retries, or deployment side effects outside the owning service's approval boundary.

## 4. Definition of Done — mandatory for every phase

A phase may be marked **done** only when all applicable items have verifiable evidence:

- The stated capability exists in source code and has a bounded, documented responsibility.
- At least one dependent phase consumes it through a stable, versioned interface; an isolated module is not an integrated phase.
- Unit and integration tests cover success, invalid input, authorization denial, failure/recovery and relevant concurrency/idempotency paths.
- Security boundaries fail closed. Caller-controlled content is untrusted; permissions are server-owned; credentials and sensitive payloads do not enter logs or public errors.
- Operations have correlation IDs, structured audit/logging and meaningful health/readiness as appropriate.
- Time/token/cost limits, cancellation and emergency stop exist where execution or autonomy is involved.
- ADRs and operational documentation cover material architectural choices, migrations, rollback and compatibility.
- Exact-head CI is green before merge and relevant mainline checks are green after merge.
- Runtime, Telegram, device, remote database and deployment acceptance are recorded separately from unit tests and CI. A test fixture is not live acceptance.
- The phase has an explicit owner, acceptance criteria, residual-risk statement and evidence links.

Suggested status values: **unassessed**, **in progress**, **blocked**, **implemented — integration pending**, **integrated — validation pending**, **done**. Never infer `done` from PR count, checked boxes in an older plan, green CI alone or a deployment workflow that did not verify the live service.

## 5. Cross-project release and safety gates

- No public Website request may inherit private Hub memory, credentials, tool grants or execution context.
- EL_AI private Hub access requires explicit owner pairing and revocable least-privilege credentials.
- EL_IR_BOT transports messages and delivery state; it does not override Hub policy or grant tool permissions.
- Unknown Telegram delivery outcomes must remain distinguishable from confirmed delivery; do not automatically replay ambiguous non-idempotent side effects.
- Desktop/local agent operations must be sandboxed, explicitly scoped, audited, reversible and bounded; no unrestricted filesystem or OS control.
- Schema migrations are additive, versioned, integrity-checked and tested against isolated fixtures. Production migration/deployment requires separate preflight, backup/restore evidence and explicit owner release.
- Paid infrastructure, external publishing, provider spend, secret rotation and production changes have distinct approval and verification records. Source changes and CI do not prove those operations occurred.
- Main branch protection and required status checks are repository governance gates. At this baseline, all four requested repositories reported `main.protected=false`; configure and independently verify protection before relying on main as a guarded release branch.

## 6. Immediate execution queue from this baseline

1. Finish exact-head CI repair and security review for Hub PR #605; preserve sanitized caller-error behavior and validate live permission rechecks.
2. Finish exact-head CI for Hub PR #607 while keeping it Draft. Review the full Render plan, Workspace Auto Sync and recurring service/disk charges before any provisioning.
3. Reconcile the canonical EL_AGENT versus requested EL_IR_BOT product boundary in an ADR.
4. Map the current Hub roadmap phases 0–7 and EL_AI milestones 0–6 onto this inventory without translating checkboxes into phase completion claims.
5. Publish consumer-driven contract tests before enabling A7, B7/B8, E5/E10 or X9.
6. Capture separate live-acceptance evidence for Cloudflare/D1, Telegram, Windows and Android; do not substitute CI for these gates.

## 7. Baseline change control

This document is a planning baseline, not a permission grant. Changes to phase ownership, dependencies, shared data boundaries or release gates require an ADR and updated contract tests. Keep source snapshots dated; refresh GitHub branch/PR/CI and runtime-control-plane evidence before each release decision.
