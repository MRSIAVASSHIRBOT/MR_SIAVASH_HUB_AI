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

The dated PR and repository snapshot above is historical. Current repository state, merge SHAs, validation and active queue are maintained in Section 5 (refreshed 2026-11-24 UTC).
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

## 5. Fresh source/CI verification — 2026-11-24 UTC

This refresh supersedes the 2026-11-23 GitHub snapshot. It distinguishes merged source and exact-head validation from post-merge mainline validation and live-operation acceptance. The Definition of Done in Section 4 remains authoritative.

### Evidence-backed phase completions

| Phase | Verified implementation and integration | Exact source evidence | Automated validation |
|---|---|---|---|
| `A1`–`A6` | Website identity/navigation, responsive system/accessibility, portfolio/status, learning center, public AI UX/content workflow and secure public Gateway | Website `main` `ea11609f0ba596c8080703fbfb285f05f908ca9f`; detailed source/deployment gates remain in Website issue #254 | PR #307 exact-head test, syntax/structure and Workflow Security Audit passed; all eight post-merge check-runs on resulting main SHA `ea11609f0ba596c8080703fbfb285f05f908ca9f` completed successfully, including Pages deployment, Gateway CI, Production/Preview Runtime Smoke, Workflow Security Audit, Scorecard, tests and syntax checks |
| `H3` | Deterministic GPI preflight, validated WorkOrder, constraints, acceptance criteria, AWI planning and authenticated planning interfaces | Hub PR #597, merge SHA `131785f504dd4401c5be2bf987090b7962a6d77c` | Mainline Backend CI, CI, security audit, defensive scan, Scorecard, video integration and Windows launcher passed at the recorded baseline |
| `H5` | Typed owner-scoped memory, provenance/confidence validation and evidence-only Agent Context authority boundary | Hub PR #597, merge SHA `131785f504dd4401c5be2bf987090b7962a6d77c`; schema migration 56 is source only | Same exact mainline validation set; owner-scope and migration regressions included |
| `H7` | Evidence-linked workflow lesson preview with owner-scoped successful-step provenance; preview does not save or approve memory | Hub PR #597, merge SHA `131785f504dd4401c5be2bf987090b7962a6d77c` | Same exact mainline validation set |
| `H8` | Typed API error envelope and sanitized HTTP detail boundary | Hub PR #597, merge SHA `131785f504dd4401c5be2bf987090b7962a6d77c`; H11 adds regression that unknown model profile identifiers are removed from public errors | Same exact mainline validation set at the baseline |
| `E4` | Dependency-aware Telegram task plans, persisted pause/resume, stable Hub idempotency keys and owner-pause revalidation before each subsequent dispatch | EL_AI PR #119, merge SHA `11f6145f372275bf6986bda80427b99dc46b54c` | Exact PR-head Python 3.11/3.12 and Workflow Security Audit passed; post-merge CI, security audit and Scorecard passed |
| `B1` | Telegram webhook receive/send transport with owner/private-chat boundary and bounded input handling | EL_IR_BOT Worker on `main` `7e994f6956a6e3a5786bda80427b99dc46b54d29` | Exact-main Worker Node 22 tests, Workflow Security Audit and Scorecard passed; transport and unauthorized/invalid-input regressions are in `tests/test_worker.mjs` |
| `B2` | Telegram webhook delivery state/ack fencing, duplicate prevention and stale-release-after-reclaim regression | EL_IR_BOT PR #24, merge SHA `7e994f6956a6e3a5786bda80427b99dc46b54d29` | Exact PR-head Worker Node 22, dependency audit and Workflow Security Audit passed; exact-main tests/security/Scorecard passed |
| `B3` | Durable D1 job queue with encrypted payloads, idempotent admission, bounded queue capacity, leased claims and lease-token hashes | EL_IR_BOT Worker/schema at `7e994f6956a6e3a5786bda80427b99dc46b54d29`; EL_AI bridge client consumes the pull/complete contract | Exact-main Worker Node 22, EL_AI Python CI and bridge-client contract tests passed; end-to-end encrypted queue/pull/completion regression passed |
| `B4` | Bounded retry/backoff, Telegram `retry_after`, retry budget, terminal states, quarantine of ambiguous sends and no automatic replay of `delivery_unknown` | EL_IR_BOT Worker and migrations 0002/0003 at `7e994f6956a6e3a5786bda80427b99dc46b54d29` | Worker retry/quarantine/ambiguous-outcome regressions and migration tests passed on exact main; EL_AI shutdown/backoff/lease-preservation tests passed |
| `B5` | D1 persistence, additive schema migrations, delivery-attempt audit, nonce storage and preservation of encrypted/unknown records | EL_IR_BOT `cloudflare/schema.sql`, migrations 0002–0004 and `tests/test_d1_migrations.py` on `7e994f6956a6e3a5786bda80427b99dc46b54d29` | Migration fixture applies the sequence and verifies preserved ciphertext, quarantined states, constraints and unique delivery-attempt identities; exact-main tests passed |
| `B6` | Telegram webhook secret validation, constant-time comparison, HMAC-SHA256 bridge authentication, timestamp window, one-use nonce, 32-byte queue encryption key and owner-only/private-chat checks | EL_IR_BOT Worker; EL_AI `TelegramBridgeClient`; Hub pairing/scoped identity contract | Exact-main EL_IR_BOT security audit, EL_AI security audit and tests passed; unsigned/replayed bridge requests, invalid secrets and non-owner commands are covered |
| `B7` | EL_AI bridge integration: signed pull/complete client, strict bounded JSON/job parsing, lease-token completion, stop-aware worker, cancellation and bounded retry | EL_IR_BOT signed bridge endpoints plus EL_AI `src/el_ai/telegram/bridge.py` and bridge runtime on `57b8289fddbc53c4e7ee1709066939467770f3a0` | EL_AI exact-main CI, Workflow Security Audit and Scorecard passed; 16 client-protocol tests, 12 worker lifecycle tests and Worker end-to-end queue/pull/complete regression passed |
| `B8` | Hub integration through EL_AI owner commands and scoped HubClient routes; owner pairing, task/result/memory/video scopes and versioned hybrid contract | Hub contract manifest `contracts/hybrid/v1/manifest.json`; EL_AI pinned consumer fixture `tests/fixtures/hub-hybrid-manifest-v1.json` (same source blob SHA); Hub `main` `6166a16c75da1520139e9eae7d9ffbbe3afa88f4`; EL_AI `main` `5cbbd7c4fed09e61556184859641331398305757` | Hub manifest/OpenAPI/scope compatibility tests, EL_AI pinned consumer compatibility tests, HubClient scoped route tests, and both repositories' exact-main CI/security/Scorecard passed |

These **19 phase IDs** (A1–A6, H3, H5, H7, H8, E4 and B1–B8) are the current source + integration + automated-validation baseline. This does not mean production acceptance: Website Preview/Production deployment and D1 migrations remain gated; H5/H7 did not alter live memory; E4 did not submit a real Telegram/Hub task; B1–B8 were validated in source, fixtures and cross-project CI but no live Cloudflare migration, Worker deployment, production Telegram send or production pairing was performed. EL_IR_BOT and EL_AI `main` CI/security/Scorecard runs completed successfully on their current SHAs; branch protection remains disabled and must be handled separately by an owner/admin.

### Current-turn merged implementation and phase gates

| Phase slice | Source/merge evidence | Exact-head result | Current status |
|---|---|---|---|
| `H11` owner approval | Hub PR #605, merge SHA `e963e1d85ec26b824881b09dc10bbffd94c68925`; action-bound, expiring, single-use receipts bind canonical inputs and ToolDefinition fingerprints, re-check current owner permissions, and consume with audit | 14 exact-head checks passed before merge | Merged; all 15 check-runs on the post-H19 main SHA `6166a16c75da1520139e9eae7d9ffbbe3afa88f4` completed successfully on 2026-11-24, including Backend CI, Python 3.11/3.12, Workflow Security Audit, Defensive Scan, Scorecard, Video Render Integration and Windows Launcher. Live trust-boundary acceptance remains separate |
| `H4` capability-gap contracts | Hub PR #612, merge SHA `e9bcd33a52dc2e9875dc50854a97c072b1e20e65`; tests cover exact case-insensitive registered tool names, deterministic order/de-duplication, bounded/malformed catalogs, and no-handler-execution behavior | 13 exact-head checks passed before merge | Merged; the post-H19 main SHA `6166a16c75da1520139e9eae7d9ffbbe3afa88f4` had 15/15 completed successful check-runs, including the Python matrix, Backend CI and security/quality workflows. The capability-gap evaluator is consumed by authenticated GPI planning routes; H6's registry exposes typed schemas, policies, catalog and lifecycle and is consumed by the agent orchestrator |
| `H19` FFmpeg quality gate | Hub PR #614, merge SHA `6166a16c75da1520139e9eae7d9ffbbe3afa88f4`; Windows FFmpeg installation uses a pinned 9.1 archive with SHA-256 verification, and keeps real MP4/FFprobe checks intact | 9 exact-head checks passed: Python 3.11/3.12, Backend CI, Linux/Windows MP4, Windows wheel smoke, workflow security audit and defensive scan | Merged; all 15 check-runs on the post-H19 main SHA `6166a16c75da1520139e9eae7d9ffbbe3afa88f4` completed successfully on 2026-11-24 |
| `E13` credential lifetime | EL_AI PR #120, merge SHA `71f657d5d08770b1981fa41e03566bc1f4bc461c`; exact-integer and positive/range validation rejects bool, float, string, non-positive and unrepresentable lifetimes | Python 3.11/3.12 and Workflow Security Audit passed; post-merge CI/security/Scorecard passed | Focused security contribution only; not completion of all E13 |
| `E13` Render private-host opt-in | EL_AI PR #121, merge SHA `5cbbd7c4fed09e61556184859641331398305757`; forwards the existing explicit opt-in to HubClient without relaxing defaults | Python 3.11/3.12 and Workflow Security Audit/Scorecard passed; post-merge CI/security/Scorecard passed | Focused integration/security contribution only; not completion of all E13 |
| `B7` completion-size contract | EL_IR_BOT PR #26, merge SHA `e3d746e739dc8445ad08b64524eaf6de3e5b533c`, safely caps local Bridge replies at 3900 UTF-16 units; EL_AI PR #124, merge SHA `57b8289fddbc53c4e7ee1709066939467770f3a0`, rejects replies above the same limit before network I/O; Worker E2E PR #27, merge SHA `2e881ab1a5d3c8350a7dec8d476e62142d345657`, verifies exact-boundary acceptance and oversized rejection | Exact-head Python 3.11/3.12, Worker Node 22, dependency audit and Workflow Security Audit passed; post-merge EL_AI CI/security/Scorecard and EL_IR_BOT tests/security/Scorecard passed | Focused B7 contract hardening within an already-counted phase; no new phase ID and no live Telegram acceptance claimed |

### Fresh repository snapshot

| Repository | Current `main` SHA | Open PRs | Current mainline workflow evidence |
|---|---|---|---|
| Hub | `46287169cfc0b1825c722e5acba4fac59d371697` | #618 Draft Render isolation | All 7 current-main workflows completed successfully: CI, Backend CI, Video Render Integration, Windows Launcher Validation, Workflow Security Audit, Defensive Python Scan and OpenSSF Scorecard |
| EL_AI | `57b8289fddbc53c4e7ee1709066939467770f3a0` | None | Post-merge CI, Workflow Security Audit and OpenSSF Scorecard all passed after PR #124 |
| Website | `0a83d34fe48008ef9871b01743a02267a7ab83b9` | None | Gateway CI, Pages deployment, Workflow Security Audit, OpenSSF Scorecard and both Cloudflare Runtime Smoke workflows all passed on this exact main SHA |
| EL_IR_BOT | `2e881ab1a5d3c8350a7dec8d476e62142d345657` | None | Worker tests, Workflow Security Audit and OpenSSF Scorecard all passed after PR #27; B7 completion-boundary tests are in main. No live D1 migration or deployment |

All four repositories report `main.protected=false`. No branch-protection settings were changed; this remains an owner/admin governance task.

### Current implementation PR status

- [PR #605 — H11 action-bound owner approval](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_HUB_AI/pull/605) merged as `e963e1d85ec26b824881b09dc10bbffd94c68925`; all 14 exact-head checks passed.
- [PR #608 — 73-phase baseline](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_HUB_AI/pull/608) merged as `e4bb95019eb86efedfa8b6e53ad8f432831eb8db`.
- [PR #612 — H4 capability-gap contract coverage](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_HUB_AI/pull/612) merged as `e9bcd33a52dc2e9875dc50854a97c072b1e20e65`; 13 exact-head checks passed.
- [PR #614 — H19 pinned Windows FFmpeg](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_HUB_AI/pull/614) merged as `6166a16c75da1520139e9eae7d9ffbbe3afa88f4`; all 9 exact-head checks passed.
- [PR #618 — Render Hub/EL_AI isolation](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_HUB_AI/pull/618) remains Draft and is based on current Hub main `46287169cfc0b1825c722e5acba4fac59d371697`. It pins EL_AI to latest merged main `57b8289fddbc53c4e7ee1709066939467770f3a0`, separates Hub and EL_AI service state/secrets, and disables service-level auto-deploy. Exact-head Linux/Windows MP4 integration, Windows wheel smoke, runtime smoke, startup/backup regressions, PowerShell parse, security audit and defensive scan passed; Backend CI and Python 3.11/3.12 CI are still running at this refresh. The Blueprint declares two Starter compute services and two persistent disks. Do not sync or provision until the account owner/guardian reviews the complete current plan and recurring charges, confirms Workspace Blueprint Auto Sync is disabled, and explicitly authorizes the cost.

EL_IR_BOT PR #25 was closed as superseded; PRs #26 and #27 are merged. EL_AI PRs #120, #121 and #124 are merged. Hub PRs #615 and #617 were closed as superseded; #618 is the current Draft. No production D1 migration, Telegram traffic, Worker deployment or paid Render provisioning was performed.

## 6. Cross-project release and safety gates

- No public Website request may inherit private Hub memory, credentials, tool grants or execution context.
- EL_AI private Hub access requires explicit owner pairing and revocable least-privilege credentials.
- EL_IR_BOT transports messages and delivery state; it does not override Hub policy or grant tool permissions.
- Unknown Telegram delivery outcomes must remain distinguishable from confirmed delivery; do not automatically replay ambiguous non-idempotent side effects.
- Desktop/local agent operations must be sandboxed, explicitly scoped, audited, reversible and bounded; no unrestricted filesystem or OS control.
- Schema migrations are additive, versioned, integrity-checked and tested against isolated fixtures. Production migration/deployment requires separate preflight, backup/restore evidence and explicit owner release.
- Paid infrastructure, external publishing, provider spend, secret rotation and production changes have distinct approval and verification records. Source changes and CI do not prove those operations occurred.
- Main branch protection and required status checks are repository governance gates. All four repositories currently report `main.protected=false`; configure and independently verify protection before relying on main as a guarded release branch.

## 7. Immediate execution queue from this baseline

1. Keep [PR #618](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_HUB_AI/pull/618) Draft until the account owner/guardian reviews the complete current Render Blueprint plan and recurring charges, confirms Workspace Blueprint Auto Sync is disabled, and explicitly authorizes any manual sync/provisioning; green CI is not provisioning approval.
2. Reconcile the canonical EL_AGENT versus EL_IR_BOT product boundary in an ADR before cross-project contracts depend on that ownership decision.
3. Publish consumer-driven contract tests before enabling A7, B7/B8, E5/E10 or X9; the B7 completion UTF-16 limit is now covered at Worker and both Python producer boundaries.
4. Capture live-acceptance evidence separately for Cloudflare/D1, Telegram, Windows and Android; do not substitute CI for live acceptance.
5. Configure and independently verify branch protection on all four repositories as an owner/admin governance action; all four currently report `main.protected=false`.

## 8. Baseline change control

This document is a planning baseline, not a permission grant. Changes to phase ownership, dependencies, shared data boundaries or release gates require an ADR and updated contract tests. Keep source snapshots dated; refresh GitHub branch/PR/CI and runtime-control-plane evidence before each release decision.


## 9. Fresh ecosystem evidence refresh — 2026-11-25 UTC

This checkpoint supersedes the repository SHAs and active-queue observations above. It does not retroactively promote partial implementation slices to whole-phase completion. Section 4's Definition of Done remains authoritative.

### Current repository snapshot

| Repository | Current `main` SHA | Open PRs | Source/CI observations |
|---|---|---|---|
| Hub | `56f47c19bf986db44d2930c78a7c0f23d10f9c63` | #618 Draft | Latest Backend CI, CI, Windows Launcher and OpenSSF Scorecard observations were successful. PR #618's base snapshot is older than this current main and must be reconciled before review. |
| EL_AI | `b68872c32b98ef224e10a0eb7bdb92afe74b6770` | None | Latest CI, Worker tests, Workflow Security Audit and OpenSSF Scorecard observations were successful. No live Telegram token, webhook or production deployment is verified. |
| Website | `c059a01bf0fcfeb622dc3b12efa6b6625879248a` | None | A12 PR #312 merged; the post-merge workflow and all eight check-runs succeeded, including repository quality, D1 isolated migration tests, browser E2E, accessibility, Gateway tests, runtime smoke, security audit, Scorecard and Pages deployment. |
| EL_IR_BOT | `a7c810d2ab653147a07ebccfafdffa45b781190d` | None | B11 PR #31 merged; post-merge Python 3.11/3.12, Worker Node 22, dependency audit, Workflow Security Audit and Scorecard succeeded. No production deployment or live Telegram traffic is verified. |

All four `main` branches still report `protected=false`. This remains an owner/admin governance task; no branch protection was changed in this refresh.

### New merged evidence since the 2026-11-24 checkpoint

- **Website A12 slice:** PR #312, [merged commit](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_AI/commit/c059a01bf0fcfeb622dc3b12efa6b6625879248a). Implements consented, privacy-minimized daily aggregates, an Access-protected admin report and the additive D1 migration source `0009_privacy_safe_analytics.sql`. The GitHub Pages site was publicly deployed at [the website URL](https://mrsiavasshirbot.github.io/MR_SIAVASH_AI/) and the deployment verifier checked 33 public assets against this exact commit. This proves static-site publication only. Migration 0009 was **not** applied to any remote D1 database; Cloudflare Production Worker deployment and production data operations were **not** performed. The slice is not by itself a declaration that all A12 acceptance criteria are complete.
- **EL_IR_BOT B11 delivery quarantine slice:** PR #31, [merged commit](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_EL_IR_BOT/commit/a7c810d2ab653147a07ebccfafdffa45b781190d). Hardens atomic review/audit state transitions for ambiguous delivery outcomes and passed exact-head plus post-merge checks. This is focused B11 hardening, not proof of a live release or full B11 operational acceptance.

These are additional implementation and validation evidence, not new whole-phase IDs. Keep the existing 19 phase-ID baseline unchanged until each affected phase is re-assessed against all applicable Definition of Done criteria and linked to stable dependent-phase integration.

### Current cross-project blockers and contract gaps

1. **Hub / Render (#618):** keep Draft. Its Blueprint declares two Starter compute services and two persistent disks, creating recurring costs; it also has branch-sync behavior that requires owner review. Do not provision, approve or merge this infrastructure PR until the account owner/guardian reviews the exact current plan, recurring charges and auto-sync behavior and explicitly authorizes the cost. Its base snapshot must first be refreshed against current Hub main.
2. **Hub AWI bridge / EL_AI E8:** Hub's `WorkOrder` and `ExecutionPlan` models include natural-language acceptance criteria and per-step criterion coverage, but the current Telegram-specific `/agent/plan-preview` contract returns only bounded step descriptions. EL_AI persists descriptions/dependencies, not a versioned acceptance-criteria contract. EL_AI `/taskplanevaluate` is read-only structural result-evidence validation; it does not prove semantic goal completion. Hub ADR-0044 remains **Proposed**, and `docs/architecture/evidence-driven-correction.md` explicitly limits persisted evaluation to `tool_execution_only`. Do not infer criteria from task descriptions, and do not claim semantic acceptance evaluation until a versioned, typed, owner-scoped plan/result contract is integrated and tested across Hub and EL_AI.
3. **EL_AI issue #107:** its older backlog text references PR #106 as a Draft review item. PR #106 has since merged (merge commit `0ffa8aa7c0815a3c77c12ac92c546488b4889d95`). Refresh the issue against current main rather than treating the old draft status as current. The merge does not imply live Telegram activation.
4. **Website release (#254):** A12's D1 migration file and Cloudflare release preflights are source changes only. Preview/Production Worker deploy, remote D1 migration, backup/restore rehearsal and post-deploy verification remain separate gates. Do not treat Pages deployment as Gateway or D1 production release.
5. **EL_IR_BOT privacy/release (#1, #18):** the privacy/authorization review and operational release gate remain open. Keep production deployment, remote D1 migration, webhook registration and live Telegram traffic blocked until the privacy boundary is reviewed, the release checklist is satisfied, and a separate explicit release authorization is recorded. Do not enable credential collection, covert tracking, biometric identification or sensitive-trait inference.
6. **Canonical product taxonomy:** the previously recorded EL_AGENT versus EL_IR_BOT discrepancy remains unresolved. Do not silently reclassify either product or introduce a shared contract that assumes they are identical.

### Current execution order

- Continue parallel, isolated source/test work only where published contracts are stable.
- First reconcile Hub ADR-0044 and define a versioned, typed acceptance-criteria/result-evidence contract shared by Hub and EL_AI; keep semantic evaluation disabled until results carry independently verifiable evidence.
- Refresh EL_AI issue #107 and Website issue #254 with current merged evidence and remaining release gates.
- Continue EL_IR_BOT defensive privacy review without expanding sensitive-data collection.
- Keep paid Render provisioning, Cloudflare Production changes, remote D1 migrations, Telegram live traffic, secrets and branch-governance changes outside automatic merge/deploy actions until their specific approvals and environment evidence exist.
- For every PR, require exact-head CI success, review its diff against the current base, merge only when the dependency contract is stable, and verify post-merge mainline checks separately.


## 10. Implementation-wave checkpoint — 2026-11-25 UTC

This checkpoint supersedes the earlier Section 9 repository snapshot and PR queue. The conservative whole-phase baseline remains 19 IDs; the 54 other IDs are **not yet whole-phase evidence verified**, which does not assert that their repositories contain no source. See `IMPLEMENTATION_WAVES_AND_LEARNING_TRACK_2026-11-25.md` for the full 73-ID inventory, the status vocabulary, parallel implementation waves and the separate owner learning/acceptance track.

### Current main snapshots

| Repository | Current main SHA | Open implementation PRs |
|---|---|---|
| Hub | `8d448f6824edaedf01ed545b82bc7dcf95b6850e` | #624 GPI/AWI plan-preview producer; #618 Draft Render resources |
| EL_AI | `fd4ed4d5c574614e07e897fe9127070ab900bd84` | #132 Draft consumer for versioned plan criteria |
| Website | `c059a01bf0fcfeb622dc3b12efa6b6625879248a` | None |
| EL_IR_BOT | `0c7249b4b598c1af8fe1455e3e64384aaf8b4c3b` | None |

All four main branches remain unprotected. No governance settings were changed.

### Merged evidence since the preceding checkpoint

- Website A12 PR #312 merged at `c059a01bf0fcfeb622dc3b12efa6b6625879248a`; GitHub Pages static publication was verified for 33 assets. D1 migration 0009 was not applied to a remote database; Cloudflare Production Worker was not deployed.
- EL_AI E8 clarification PR #131 merged at `fd4ed4d5c574614e07e897fe9127070ab900bd84`; evaluation JSON explicitly reports `evaluation_scope=tool_execution_only`, `goal_satisfaction=not_evaluated`, and `acceptance_criteria_evaluation=not_implemented`.
- EL_IR_BOT B11 quarantine PR #31 merged at `a7c810d2ab653147a07ebccfafdffa45b781190d`.
- EL_IR_BOT privacy-source-review PR #32 merged at `0c7249b4b598c1af8fe1455e3e64384aaf8b4c3b`. It documents source behavior; it is not a security certification and does not close privacy Issue #1 or release Issue #18.
- Hub PR #623 refreshed this roadmap at `8d448f6824edaedf01ed545b82bc7dcf95b6850e`.

These are implementation slices and evidence updates; they do not increase the 19 whole-phase count without a phase-by-phase Definition of Done review.

### Current cross-repository integration

- Hub PR #624 proposes the additive producer contract `telegram_agent_plan.v1`, reusing GPI WorkOrder and AWI ExecutionPlan while preserving the legacy description-only `steps` field. It remains unmerged pending the final exact-head test matrix.
- EL_AI PR #132 consumes this versioned contract and stores bounded acceptance criteria and step mapping in TaskPlan schema v4, with v1-v3 migration compatibility. It remains Draft pending Hub producer merge and post-merge checks.
- Neither preview route creates a Task or invokes tools. Semantic goal evaluation remains deliberately unavailable; a planning label such as `ready_for_review` is not a passed criterion or an execution authorization.

### Active WIP implementation branches

The following branches are source work in progress, not merged phase completions:

- Hub roadmap/learning wave: `roadmap/implementation-waves-learning-track-20261125`, commit `aa53a53aa06ce96f532fc811dd134303e8a8e06d`.
- Hub H10 evaluation-scope clarity: `fix/h10-explicit-evaluation-scope-20261125`, latest commit `8b4fe60f8eef2c518202f85a4d28a0f107a8788f`. It adds explicit tool-only scope fields in the workflow evaluation payload and a focused regression assertion; semantic acceptance remains not implemented.
- Website A13 SSE response hardening: `fix/a13-sse-security-headers-20261125`, latest commit `4d55e39344e6e0968f89439822c69e1b20f99517`. It adds the same frame-denial/CSP headers used by JSON responses to the streaming response and asserts those headers in the SSE contract test.

These branches intentionally remain unmerged WIP until their implementation wave is grouped and the final exact-head test matrix is run. They must be refreshed/rebased against current main before final review. No PR is marked complete merely because its source files and tests have been authored.

### Owner learning track

The project owner can start with non-production, reversible work while engineering continues:

1. Review the `telegram_agent_plan.v1` contract and write a harmless two-step local sample with one dependency and explicit acceptance criteria.
2. Inspect a Hub evaluation result and explain why successful tool execution does not imply end-to-end goal satisfaction.
3. Review the Persian preview/clarification messages in EL_AI and report wording/UX defects.
4. Draw the public website ↔ Hub ↔ EL_AI ↔ Telegram Bridge trust boundaries and identify which service owns each identity/task/delivery.
5. Decide the canonical product boundary between `MR_SIAVASH_EL_AGENT` and `MR_SIAVASH_EL_IR_BOT` so the architecture decision can be recorded before dependent cross-product work.

Do not use production secrets, live Telegram webhooks, paid infrastructure, or remote database migrations for these learning tasks.

### Test cadence

Small implementation edits may be accumulated between full-suite checkpoints, but focused regression cases are kept alongside code changes. Before a PR leaves Draft or is merged, all required checks must pass on its exact current head; after merge, the relevant mainline checks must pass. Never merge untested code or treat a pending/old-head run as a pass.

### Blockers unchanged

- Hub Render PR #618 is Draft; its recurring compute/storage cost and autosync behavior require separate account-owner/guardian review and explicit cost authorization.
- Website Preview/Production Worker releases, remote D1 migrations, backup/restore and Production changes remain separate owner-approved gates.
- EL_IR_BOT privacy Issue #1 and release Issue #18 remain open; no live Telegram traffic or webhook registration.
- Branch protection remains disabled on all four repositories and is an owner/admin governance task.
- The EL_AGENT vs EL_IR_BOT product taxonomy remains unresolved.


### Typed planning response contract update — 2026-11-25

Hub PR #624 now includes a typed `TelegramAgentPlanPreviewResponse` envelope in addition to the nested `telegram_agent_plan.v1` criteria contract. The envelope preserves `provider_mode`, `provider`, `model`, legacy description-only `steps`, nested `plan_contract`, and explicit `execution_started=false` / `tasks_created=0` fields. The endpoint declares this response model so OpenAPI consumers can discover the contract without reverse-engineering a generic dictionary.

A focused OpenAPI regression has been added to verify the endpoint response reference, legacy projection, nested contract schema and non-execution constants. It has not yet been executed; the full exact-head test checkpoint is deferred until this implementation wave is grouped. PR #624 remains open and unmerged.

Current WIP branch commits (not merged, not phase-completion evidence):
- Hub H10 evaluation-scope clarity: `fix/h10-explicit-evaluation-scope-20261125`, `8b4fe60f8eef2c518202f85a4d28a0f107a8788f`.
- Hub GPI/AWI producer contract: `feat/telegram-gpi-awi-contract-20261125`, latest response-model/test commits `afcda9847b207bf61db6c99264566a885582a972` and `ba17f76365b0a77370fd1f809d5d022d9c94fa32`.
- Website A13 SSE response hardening: `fix/a13-sse-security-headers-20261125`, `4d55e39344e6e0968f89439822c69e1b20f99517`.
- Hub 73-phase implementation/learning map: `roadmap/implementation-waves-learning-track-20261125`, latest plan doc commit `756f2eb685ffebd69da2ea3b5a9f650d3ecfbce5`.

All four `main` branches remain unchanged by these WIP branches. Do not claim exact-head test success or merge readiness for untested WIP.


### Follow-up cross-project edge-case gates — 2026-11-25 UTC

The consumer-side E8 validator now verifies not only the Pydantic/JSON field shapes, but also the logical readiness relationship:

- Non-empty `missing_information` must have at least one `clarification_question`.
- `research_required=true` must include at least one `research_question`.
- Research questions are invalid when `research_required=false`.
- `planning_status` must exactly equal the deterministic precedence: clarification required → research required → ready for review.

This closes a fail-open condition where a contradictory `ready_for_review` label could otherwise be accepted with unresolved information. Regression fixtures for valid clarification/research cases and contradictory states were updated in EL_AI PR #132. Latest consumer head at this checkpoint is `d13385e603743b5fa3eef26e15340fa1d7183788`; exact-head Python 3.11/3.12 and Workflow Security checks were observed green. The full final matrix has not been rerun after the newest readiness-consistency edits.

Website A13 branch has an additional resource-boundary check: complete upstream SSE frames as well as incomplete buffers are now checked against 32 KiB before parsing, with a regression test for a single oversized complete frame. Latest A13 branch head is `30f02e29150d423fb2b24fc0944757672b738293`. Its full tests have not been run on this head.


### B10 telemetry minimization and product taxonomy ADR — 2026-11-25

- EL_IR_BOT WIP branch `fix/b10-redact-telegram-update-ids-20261125` removes Telegram `update_id` from retry/failure log events while retaining it in D1 delivery/idempotency state where required. The retry log retains only attempt count, delay and fixed reason code. Regression coverage was added but not yet executed on the WIP head.
- ADR-0045 (`docs/architecture/adr-0045-product-taxonomy-el-agent-vs-el-ir-bot.md`) is Proposed and owner-decision-required. It records the distinction between the canonical Windows/Android EL_AGENT and the current Telegram Bridge EL_IR_BOT. The temporary recommendation is to keep the current four-repository 73-phase campaign intact and track EL_AGENT separately until the owner decides whether to expand/restructure the phase inventory.


### Consolidated WIP branch ledger — 2026-11-25 UTC

- Hub H10: `fix/h10-explicit-evaluation-scope-20261125`, `8b4fe60f8eef2c518202f85a4d28a0f107a8788f`.
- Hub producer/X1: PR #624 branch `feat/telegram-gpi-awi-contract-20261125`, `ba17f76365b0a77370fd1f809d5d022d9c94fa32`; OpenAPI response contract added; primary test job pending at last check.
- EL_AI E8 consumer: PR #132 branch `feat/e8-store-versioned-acceptance-contract-20261125`, `d13385e603743b5fa3eef26e15340fa1d7183788`; exact-head Python 3.11/3.12 and security checks green at last check; Draft pending Hub producer.
- Website A13: `fix/a13-sse-security-headers-20261125`, `1e1ca88ddde3cb9f5c0acaae75d9ba6b928a6f8a`; SSE security headers and complete-frame size guard added with regression coverage; full matrix deferred.
- EL_IR_BOT B10: `fix/b10-redact-telegram-update-ids-20261125`, `4688709bdbba3a83f7bc80cfec73243799575f02`; Worker telemetry no longer logs Telegram update IDs; D1 idempotency state remains unchanged.
- Hub roadmap/learning and ADR: `roadmap/implementation-waves-learning-track-20261125`, `0df40341ecb28d3ed9e90ce1b0e7590ec940567d`; proposed ADR-0045 at `4e0c3e3bfe1a0c349234e3088201166843ce299c`.

All entries above are WIP and do not increase the 19 whole-phase evidence baseline.


### A13 UTF-8 byte-boundary follow-up — 2026-11-25 UTC

The latest Website A13 WIP head is now `23869f535eadea32baae16b341f3ead04651963c` (source commit `2b24a637c0c157fdad0b825aba09f1905557cb97`). The SSE stream enforces the 32 KiB limit against UTF-8 byte length for both complete frames and incomplete buffers. Its regression fixture uses a multibyte string whose UTF-16 code-unit count is below 32 KiB while its UTF-8 byte length exceeds the limit. This closes the character-count/byte-count mismatch in the earlier test design. The full Gateway CI matrix has not yet been run on this WIP head.
