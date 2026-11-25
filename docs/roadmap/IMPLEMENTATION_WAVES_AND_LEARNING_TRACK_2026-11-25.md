# Ecosystem implementation waves and learning track

**Checkpoint:** 2026-11-25  
**Scope:** Hub, EL_AI, public website, EL_IR_BOT and shared contracts  
**Purpose:** Coordinate one broad implementation campaign without collapsing independent products into one unsafe mega-PR.

## 1. Operating decision

The 73-phase inventory is a roadmap, not evidence that 73 independent changes can safely be merged at once. Work proceeds concurrently behind versioned contracts, but the integration sequence remains dependency-aware.

The implementation campaign uses two parallel tracks:

- **Engineering track (assistant):** inspect current source, design contracts, implement modules, add regression coverage, integrate consumers, maintain migration compatibility, prepare PRs and verify final exact-head/mainline checks.
- **Owner learning/acceptance track (Siavash):** make product/architecture decisions, review Persian UX and acceptance criteria, reproduce selected non-production tests locally, inspect evidence and gradually take ownership of small implementation tasks. This is a distinct workstream, not duplicate editing of the same files.

The user-requested test deferral means **do not run the entire expensive matrix after every small implementation commit**. Group changes into coherent checkpoints and run focused tests where a change is risky. Before merge, every PR must still pass its complete required exact-head checks; after merge, verify the mainline checks. No untested code is merged into main.

A long-lived Draft PR is not a substitute for a clean branch. Each implementation wave should have bounded ownership, explicit dependencies, one versioned contract and a clear acceptance checklist. Rebase/refresh against current main before final review; do not close a useful branch merely because it has been open for a while.

## 2. Evidence baseline

### Whole-phase evidence currently verified

The conservative baseline still contains **19 phase IDs** with source, integration and automated-validation evidence:

- Hub: `H3`, `H5`, `H7`, `H8`
- EL_AI: `E4`
- Website: `A1`–`A6`
- EL_IR_BOT: `B1`–`B8`

This is not a claim of Production acceptance, live Telegram operation, remote D1 migration, device acceptance, or unrestricted autonomous execution.

### Partial implementation evidence / current integration work

These IDs have useful source or merged slices, but are **not promoted to whole-phase completion** by this checkpoint:

- Hub: `H4`, `H11`, `H19`; `H6` has a source registry/orchestrator footprint that still needs phase-level audit.
- EL_AI: `E8` has structural evidence review and a Draft consumer contract PR; `E13` has focused credential-lifetime/host opt-in security contributions.
- Website: `A12` has a merged consented aggregate-analytics slice; remote D1 and Worker release acceptance are separate.
- EL_IR_BOT: `B11` has delivery-quarantine hardening and a privacy-source-review document; privacy and release acceptance remain open.
- Shared: `X1` has a versioned hybrid manifest/consumer fixture footprint; canonical cross-repository ownership still needs reconciliation.

### IDs not yet demonstrated as whole-phase complete

Every other ID in the inventory below remains **audit pending**. This does not mean no source exists. It means the full Definition of Done has not yet been established with current source, dependent integration, exact-head tests, security/operations evidence and residual-risk review.

## 3. Full 73-phase inventory and first next action

Statuses: **Verified** = in the 19-ID whole-phase baseline; **Partial** = a known implementation slice exists; **Audit pending** = inspect current source and tests before deciding what is missing.

### Hub — H0 through H20

| ID | Capability / phase objective | Status | First engineering action |
|---|---|---|---|
| H0 | Repository integrity, architecture, configuration and build/test foundation | Audit pending | Inventory configuration, packaging, local bootstrap, secrets boundaries and reproducible setup |
| H1 | Workflow definition, DAG validation, stable step identity and checkpoints | Audit pending | Reconcile workflow-plan, persistence, worker leases and recovery contracts against one state model |
| H2 | AWI decomposition, dependency planning, validation and revision | Audit pending | Verify the full plan → dependency graph → revision lifecycle; test deterministic ordering and bounded replanning |
| H3 | GPI intent/context, WorkOrder, constraints and acceptance criteria | Verified | Keep WorkOrder as the planning source; integrate its criteria through versioned consumers |
| H4 | Capability registry, gap detection and matching | Partial | Audit the registered catalog, gap evaluator, policy distinction and consumers; close missing lifecycle cases |
| H5 | Risk-aware strategy and decision revision | Verified | Reconcile all strategy outputs against server-derived risk and policy |
| H6 | Tool/skill manifests, discovery, schemas, routing and lifecycle | Partial | Audit manifest versions, input/output validation, disabled tools, schema changes and lifecycle consumers |
| H7 | Execution queue, dispatch, concurrency, results and budgets | Verified | Validate remaining queue/resource-budget integration and operational telemetry |
| H8 | Retry, backoff, checkpoints, resume and unknown outcomes | Verified | Audit cross-service idempotency and recovery behavior without replaying ambiguous side effects |
| H9 | Working, episodic, semantic and procedural memory | Audit pending | Verify provenance, retention, owner scoping, retrieval/consolidation and privacy boundaries end to end |
| H10 | Evidence evaluation, goal completion, correction and replanning | Partial | Keep tool execution evidence separate from goal satisfaction; define typed, independently verifiable criterion evidence |
| H11 | Authentication, authorization, policy, grants, secrets and audit | Partial | Complete lifecycle/revocation/one-time approval integration and test every enforcement boundary |
| H12 | Versioned APIs, validation, errors, rate limits and service boundaries | Audit pending | Publish contract compatibility matrix and consumer-driven regression tests across all four repositories |
| H13 | Multi-agent registry, delegation, handoff and conflict handling | Audit pending | Define typed agent identity, delegation authority, bounded context and result aggregation before enabling delegation |
| H14 | Model/provider registry, routing, fallback and budget control | Audit pending | Audit provider policy, local/cloud selection, quota charging, timeout and fallback semantics |
| H15 | Logs, metrics, traces, health/readiness and alerts | Audit pending | Establish correlation vocabulary and privacy-safe health/metrics contract across services |
| H16 | Database, migrations, transactions, integrity, retention and backup | Audit pending | Reconcile every schema ledger and repository migration chain; test rollback/restore in isolated fixtures |
| H17 | Admin/control center for agents, tasks, tools, memory and policy | Audit pending | Map admin operations to owner scopes, audit events and non-executable previews |
| H18 | Async execution, queue performance, concurrency and quotas | Audit pending | Measure bounded load/concurrency and cancellation behavior before changing defaults |
| H19 | Continuous quality, security, CI/CD, release governance and docs | Partial | Consolidate exact-head required checks, quality gates, supply-chain validation and reproducible release evidence |
| H20 | Advanced research, adaptive planning and bounded self-improvement | Audit pending | Keep experiments isolated, resource-bounded, reviewable and rollbackable; no self-authorized policy changes |

### EL_AI — E0 through E14

| ID | Capability / phase objective | Status | First engineering action |
|---|---|---|---|
| E0 | Agent runtime, configuration and local lifecycle | Audit pending | Reproduce clean install/start/stop and configuration validation on supported Python versions |
| E1 | Owner identity, pairing and personalization | Audit pending | Verify owner binding, revocation, identity mapping and recovery behavior |
| E2 | Conversation state and context boundaries | Audit pending | Audit context isolation, message size, persistence and sensitive-data retention |
| E3 | Goal/intent understanding aligned to Hub GPI | Audit pending | Consume the canonical versioned WorkOrder; do not create a second goal parser |
| E4 | Planning/task decomposition and pause/resume | Verified | Extend only through additive versioned contracts; preserve existing checkpoints |
| E5 | Bounded execution through Hub contracts | Audit pending | Implement only after producer/consumer contracts and owner authorization semantics are stable |
| E6 | Tool/skill discovery and approved routing | Audit pending | Consume server-owned tool registry metadata; never allow model-created handlers |
| E7 | Owner-scoped memory and learning | Audit pending | Verify memory provenance, privacy, deletion and cross-project access grants |
| E8 | Evidence evaluation, correction and replanning | Partial | Finish the typed criteria/result contract; keep semantic evaluation unavailable without independent evidence |
| E9 | Model selection/routing under Hub budgets | Audit pending | Reuse Hub policy and quota contracts; test local-first and provider-denial paths |
| E10 | Telegram interface and message delivery integration | Audit pending | Separate local command tests from live webhook/send acceptance |
| E11 | Desktop/local agent with sandboxed reversible operations | Audit pending | Define a strict allowlist and dry-run/undo semantics before OS or filesystem actions |
| E12 | Bounded autonomous operations, chains, budgets and cancellation | Audit pending | Reconcile pause/cancel semantics across local plan and Hub task; no false global kill-switch claim |
| E13 | Permissions, trust boundaries, audit and context protection | Partial | Complete secret-lifetime, permission-revocation, prompt-injection and data-flow review |
| E14 | Cross-project release, monitoring and end-to-end validation | Audit pending | Build a version-matched integration matrix; separate CI, preview and live acceptance |

### Public website — A0 through A14

| ID | Capability / phase objective | Status | First engineering action |
|---|---|---|---|
| A0 | Website build, routes and deployment boundaries | Audit pending | Audit route inventory, asset pipeline, fallback/error pages and deployment ownership |
| A1 | Digital identity and navigation | Verified | Retain current source; add only evidence-backed UX improvements |
| A2 | Responsive system, accessibility, typography, motion and themes | Verified | Keep accessibility/responsive smoke in the release checkpoint |
| A3 | Portfolio, project catalogue and truthful status | Verified | Tie displayed status to the phase evidence ledger, not roadmap claims |
| A4 | Learning/knowledge center | Verified | Review content freshness, citations and accessible navigation |
| A5 | AI interface, sessions and content workflow | Verified | Audit privacy boundaries and editor-to-public publishing state |
| A6 | Public AI Gateway, validation, quotas and rate limits | Verified | Keep public/private Gateway boundaries and runtime acceptance separate |
| A7 | Authenticated private Hub integration | Audit pending | Publish/consume versioned contracts with owner auth and sanitized failures |
| A8 | Access-protected admin and append-only audit | Audit pending | Audit every mutation route, Access boundary and audit immutability |
| A9 | Content engine and publishing controls | Audit pending | Verify revisions, publish/unpublish, rollback and public published-only reads |
| A10 | Bounded public developer/AI tools | Audit pending | Ensure public tool endpoints cannot inherit private Hub grants or memory |
| A11 | Telegram/GitHub/AI integrations | Audit pending | Verify each integration's explicit scopes, token boundaries and revocation |
| A12 | Consent/minimization/retention analytics and CRM | Partial | Validate consent transitions, 90-day retention, aggregate privacy and isolated migration 0009 |
| A13 | Security, performance, SEO, caching and accessibility hardening | Audit pending | Run a consolidated static-site/Gateway hardening audit and close measurable defects |
| A14 | Production readiness, monitoring, rollback and evolution | Audit pending | Require exact source/version, Preview, backup/restore and owner-approved release evidence |

### EL_IR_BOT — B0 through B11

| ID | Capability / phase objective | Status | First engineering action |
|---|---|---|---|
| B0 | Bridge foundation, configuration and trust boundaries | Audit pending | Verify retired entrypoints are inert and all active routes fail closed |
| B1 | Telegram receive/send transport | Verified | Keep live delivery separate from source/fixture acceptance |
| B2 | Delivery state, acknowledgement and duplicate prevention | Verified | Preserve fencing and duplicate suppression |
| B3 | Durable queue, lifecycle, leases and capacity | Verified | Reconcile encrypted queue payload bounds and lease cleanup |
| B4 | Retry/backoff, quarantine and ambiguous outcomes | Verified | Never automatically replay unknown non-idempotent delivery |
| B5 | D1 persistence and additive migrations | Verified | Keep remote migration/backup evidence separate from fixture tests |
| B6 | Secrets, identity, endpoint protection and authorization | Verified | Continue owner-only/private-chat regression and secret minimization |
| B7 | EL_AI Bridge integration | Verified | Keep versioned pull/complete contract tests synchronized with EL_AI |
| B8 | Hub integration through scoped contracts | Verified | Keep least-privilege contract and owner mapping tests current |
| B9 | Media/content transport and Telegram limits | Audit pending | Remain blocked until privacy/consent review and lawful data minimization are settled; no biometric or covert collection |
| B10 | Logs, metrics, health and delivery analytics | Audit pending | Verify aggregate-only metrics, redaction, retention and health semantics |
| B11 | Tests, CI, security, deployment and release | Partial | Complete source-level threat review and release evidence; production gate remains closed |

### Shared integration — X1 through X10

| ID | Capability / phase objective | Status | First engineering action |
|---|---|---|---|
| X1 | Versioned shared API/Task/Agent/Message/Memory/Error contracts | Partial | Freeze the Hub/EL_AI plan-preview v1 contract and publish producer/consumer compatibility tests |
| X2 | Shared identity, pairing, scoped authorization and revocation | Audit pending | Define canonical owner identity and revocation propagation across services |
| X3 | Permissioned shared memory and provenance | Audit pending | Define memory-sharing policy, provenance and deletion propagation |
| X4 | Agent registry, capabilities, lifecycle and trust | Audit pending | Reconcile agent identities and ownership; resolve EL_AGENT vs EL_IR_BOT taxonomy |
| X5 | Tool/skill schemas, permissions and lifecycle | Audit pending | Define one server-owned registry contract and schema digest policy |
| X6 | Model/provider identity, capability and budget contracts | Audit pending | Publish model/provider capability and quota contract |
| X7 | Shared logs, metrics, trace IDs and health vocabulary | Audit pending | Define privacy-safe correlation and observability contract |
| X8 | Cross-service security, secrets and audit | Audit pending | Map trust boundaries and revocation across public/private/service identities |
| X9 | Authenticated cross-project workflows | Audit pending | Start only after X1/X2/X4/X5 and Hub worker gates are stable |
| X10 | Unified cross-project control plane | Audit pending | Build read-only inventory first; control actions require separate server authorization |

## 4. Implementation waves

Parallel source development is permitted within a wave. Cross-wave integration must follow published dependencies.

### Wave 0 — contract and branch stabilization

**Phases:** `H3/H12`, `E3/E4/E5/E8`, `X1`.

- Hub PR #624 provides the producer contract `telegram_agent_plan.v1` and now publishes a typed response envelope in OpenAPI, including the legacy step projection and explicit non-execution flags.
- EL_AI PR #132 is the consumer and remains Draft until the producer is merged and validated on main. Its consumer-side validator now rejects mismatches between planning_status, missing-information/clarification state and research-required state before persisting a plan.
- Keep preview planning-only: no Task creation, tool invocation or inferred authorization.
- Reconcile the open PRs before adding another producer/consumer version.

**Owner learning task:** inspect the contract fields, then write one harmless local sample goal with two steps, one dependency and two acceptance criteria. Identify which fields express planning facts and which fields explicitly state that execution/evaluation has not happened.

### Wave 1 — evidence and durable execution

**Phases:** `H1/H2/H7/H8/H10`, `E5/E8/E12`, `X1/X2/X7/X8`.

- Integrate typed criteria into durable workflow metadata only after the plan-binding contract is approved.
- Maintain the current `tool_execution_only` scope until trusted criterion verifiers and independent evidence exist.
- Preserve encrypted payloads, stable step identities, owner scoping, fenced leases, idempotency and unknown-outcome quarantine.
- Do not treat a successful tool call as proof of the user's end-to-end goal.

**Owner learning task:** reproduce the planning-only contract locally and inspect a structured evaluation report. Confirm that `goal_satisfaction` remains `not_evaluated` when only tool execution is known.

### Wave 2 — trust, identity and persistence

**Phases:** `H0/H11/H12/H16`, `E0/E1/E13`, `B0/B5/B6`, `X2/X8`.

- Audit owner mapping, permissions, secrets, D1/SQLite schema histories, retention and backup/restore.
- Keep production migrations and secrets outside code-only PRs.
- Record any architecture change in an ADR before changing ownership or cross-service trust.

**Owner learning task:** draw the four-service trust boundary and identify which service owns a user identity, a task, a Telegram delivery and a public session.

### Wave 3 — registry, model and memory

**Phases:** `H4/H6/H9/H13/H14`, `E6/E7/E9`, `X3/X4/X5/X6`.

- Make ToolRegistry, AgentRegistry and ModelRouter the only authoritative registries.
- Implement discovery as metadata, not dynamic unreviewed code installation.
- Keep memory owner-scoped, provenance-bearing and deletable.
- Keep delegation bounded by policy, budgets, cancellation and audit.

**Owner learning task:** review a registered tool's input/output schema and explain why capability presence is not permission to execute it.

### Wave 4 — website and public boundary

**Phases:** `A0`–`A14`, especially `A7/A12/A13/A14).

- Audit public/private data separation, admin authorization, content publication, Gateway limits, consent and retention.
- Complete A13 as a measurable hardening package and A14 only with Preview/rollback/Production evidence.
- Keep the public site free of private Hub memory, secrets and tool grants.

**Owner learning task:** review the Persian UX, route navigation, accessibility and public project-status claims. Flag anything that overstates a feature's deployment or autonomy.

### Wave 5 — Telegram Bridge and operations

**Phases:** `B0`–`B11`, especially `B9/B10/B11`.

- Continue only the supported owner/private-chat transport.
- Do not add credential capture, covert tracking, biometric identification or sensitive-trait inference.
- Complete retention, health, metrics and operational runbooks using synthetic/non-production fixtures first.
- Keep live Telegram traffic blocked while privacy Issue #1 and operational Issue #18 remain open.

**Owner learning task:** run the local Worker/Bridge tests with synthetic fixtures and report which delivery outcomes are confirmed, retryable or ambiguous. Do not configure live tokens or production webhooks as a learning exercise.

### Wave 6 — cross-project workflows and unified control

**Phases:** `H17/H18/H20`, `E11/E12/E14`, `X7/X9/X10`.

- Start with read-only inventory and status visibility.
- Add control actions only through server-owned auth, explicit owner scope, audited state transitions and cancellation.
- Desktop/local actions must be sandboxed, reversible and allow-listed.
- Self-improvement must never rewrite its own safety policy or grant itself permissions.

**Owner learning task:** review the local agent's dry-run output and classify each operation by reversibility and required authorization.

## 5. Owner-only and environment gates

These are not assistant coding tasks and must not be represented as complete by a source PR:

- Render PR #618 proposes recurring paid compute and persistent storage. Keep it Draft until the account owner/guardian reviews the exact resource/cost plan and separately approves any purchase or sync.
- Cloudflare Preview/Production deployment, remote D1 migrations, production secrets, DNS/routes and live traffic require their own reviewed release plan and explicit owner/admin authorization.
- EL_IR_BOT privacy Issue #1 and release Issue #18 remain blockers. No webhook registration or live Telegram traffic until those gates are independently resolved.
- GitHub main branch protection is currently disabled on all four repositories. Enabling it is a repository-admin governance change; source code cannot prove it has been configured.
- Resolve the canonical `MR_SIAVASH_EL_AGENT` versus `MR_SIAVASH_EL_IR_BOT` product boundary in an ADR before contracts assume they are the same product.

Siavash's safe starting work is local code review, UX review, non-production tests, acceptance criteria and architecture decisions. Paid provisioning, production secrets, production database changes and external releases remain owner/admin/guardian gates.

## 6. Current PR coordination

| Repository | PR | Role | State at checkpoint | Dependency |
|---|---:|---|---|---|
| Hub | #624 | GPI/AWI `telegram_agent_plan.v1` producer | Open, not merged; typed OpenAPI response model added to WIP head; exact-head tests deferred to the next integration checkpoint | Producer contract for EL_AI #132 |
| EL_AI | #132 | Versioned criteria persistence/consumer | Draft; latest exact-head Python 3.11/3.12 and Workflow Security Audit succeeded | Must wait for Hub #624 merge and post-merge checks |
| Hub | #618 | Render isolation infrastructure | Draft; recurring cost and autosync approval gate | Not part of the code-only integration wave |
| Website | none | Next A13/A14 source work | No open PR at checkpoint | Audit existing current-main source before branching |
| EL_IR_BOT | none | B9/B10/B11 defensive work | No open PR at checkpoint | Privacy/release blockers remain open |

Do not stack changes onto #624 or #132 unless they change that contract. Keep unrelated phase work on separate branches so one long-running test or decision does not block the other repositories.

## 7. Checkpoint acceptance policy

For each implementation wave:

1. Record exact base and head SHAs and changed files.
2. Preserve a stable API/schema version and document compatibility.
3. Add focused regression tests with the implementation, but defer the full expensive matrix until the wave's integration checkpoint.
4. Review authorization, data flow, failure modes, migration compatibility and rollback.
5. Run the full exact-head checks before a PR leaves Draft or is merged.
6. After merge, verify mainline checks and update the phase evidence ledger.
7. Mark a phase done only when the full Definition of Done in `ECOSYSTEM_73_PHASE_BASELINE.md` is met.

No change is counted twice. A partial PR, green lint job, source file, test fixture or Pages deployment alone is not a completed phase.

## 8. Current branches and source snapshots

- Hub main: `8d448f6824edaedf01ed545b82bc7dcf95b6850e`
- EL_AI main: `fd4ed4d5c574614e07e897fe9127070ab900bd84`
- Website main: `c059a01bf0fcfeb622dc3b12efa6b6625879248a`
- EL_IR_BOT main: `0c7249b4b598c1af8fe1455e3e64384aaf8b4c3b`

Refresh this snapshot before review or rebase. It is not evidence that remote production environments match source.


## 9. Implementation checkpoint update — 2026-11-25 UTC

The following additive implementation edits were completed after the first roadmap draft. They are WIP branches, not merged mainline features:

- Hub PR #624 producer contract branch latest head: `ba17f76365b0a77370fd1f809d5d022d9c94fa32`. Added `TelegramAgentPlanPreviewResponse` with `response_model` on the route and a focused OpenAPI contract regression for nested plan schema and explicit non-execution fields.
- EL_AI PR #132 consumer branch latest head: `d13385e603743b5fa3eef26e15340fa1d7183788`. Contract loading now derives the only valid planning status from the missing-information/clarification and research fields, and rejects mismatched or incomplete combinations before local persistence. Exact-head Python 3.11/3.12 and Workflow Security checks were green at this checkpoint. The PR remains Draft pending producer integration.
- Website A13 branch latest head: `30f02e29150d423fb2b24fc0944757672b738293`. SSE responses now align with the JSON response frame/CSP headers, and complete upstream SSE frames are checked against the 32 KiB limit before JSON parsing. Regression coverage was added; full tests have not yet been run on this WIP head.
- Hub H10 branch latest head remains `8b4fe60f8eef2c518202f85a4d28a0f107a8788f`: explicit tool-only evaluation scope fields are returned to consumers.

The test strategy for these source waves is checkpointed rather than commit-by-commit: preserve focused regression cases with the code, group implementations, then execute the complete exact-head matrix before marking a PR review-ready/merging. Any CI that runs automatically because a branch is attached to an open PR remains separately visible; pending checks are never reported as passed.


### Product taxonomy ADR

A proposed decision document now exists at `docs/architecture/adr-0045-product-taxonomy-el-agent-vs-el-ir-bot.md` (ADR-0045, status Proposed). It records the mismatch between the canonical ecosystem document's Windows/Android `MR_SIAVASH_EL_AGENT` and the current four-repository 73-phase baseline's Telegram Bridge `MR_SIAVASH_EL_IR_BOT`.

The provisional recommendation is to preserve the current four-repository execution baseline and keep EL_AGENT as a separately tracked adjacent product until the owner decides whether to expand or restructure the phase inventory. No product identity or phase ownership is changed by the ADR.


### EL_IR_BOT B10 telemetry minimization branch

A defensive B10 branch now removes Telegram `update_id` from the Cloudflare Worker's retry/failure log events while retaining it in the D1 idempotency/delivery state machine where it is operationally required. The retry log retains only the bounded attempt count, retry delay and fixed reason code.

- Branch: `fix/b10-redact-telegram-update-ids-20261125`
- Worker commit: `8d53d8bb9d6d9a79bebbc298fe43adfbfe2c8e7a`
- Regression commit: `4688709bdbba3a83f7bc80cfec73243799575f02`

This is a telemetry minimization slice, not a closure of the privacy or release gates. Exact Worker and Python test matrices have not yet been run on this WIP branch.
