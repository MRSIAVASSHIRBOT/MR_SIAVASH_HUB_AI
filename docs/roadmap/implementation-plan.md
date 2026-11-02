# Implementation Roadmap

## Delivery strategy
Build one end-to-end vertical slice before expanding module count. Prioritize reliability, local resource constraints, and the first six-month focus on social content workflows and video production.

## Phase 0 — Architecture and guardrails
- [x] Bootstrap repository
- [x] Define initial architecture
- [x] Define module ownership
- [x] Define initial threat model
- [x] Add architecture decision records
- [x] Define initial API and configuration schemas
- [x] Define initial test and quality gates

Exit criteria: module boundaries, trust boundaries, and local runtime assumptions are reviewable.

## Phase 1 — Minimal working platform
- [x] Application configuration
- [x] FastAPI application factory and health endpoint
- [x] SQLite task persistence
- [x] Task state lifecycle with cancellation
- [x] Initial policy evaluation service
- [x] Capability-aware model routing abstraction
- [x] Unit and API tests
- [x] Backend CI workflow
- [x] Structured audit event persistence with metadata allow-listing
- [x] Pull-driven worker execution with atomic task claiming, per-instance serialization, persisted results, and fail-closed handler registry
- [x] Recover stale running tasks as interrupted failures without automatic replay
- [x] Compare-and-set completion so late worker results cannot overwrite cancellation
- [x] Local owner authentication, hashed password storage, expiring/revocable sessions
- [x] Authenticated, one-time action-bound approval/rejection with approver audit identity
- [x] Bounded retry policy for explicitly safe/idempotent handler types, with persisted attempt limits and exponential backoff
- [x] Versioned SQLite schema migration tooling with transactional application, checksums, legacy-column upgrades, and unknown-version protection
- [x] Typed model-provider contract, explicit registry, capability-aware dispatch, and deterministic local stub adapter
- [x] Loopback-only Ollama local inference adapter with opt-in activation, bounded requests, health checks, and sanitized errors
- [x] Read-only host hardware report for local model planning (CPU, total/available memory, disk, and safe GPU-name probe)
- [x] Conservative RAM resource advisor with explicit model profiles, safety reserve, unknown-data handling, and no inference side effects
- [x] Explicit opt-in OpenRouter text adapter with origin restriction, bounded requests, sanitized errors, and no silent fallback; general tool-calling providers remain future work
- [x] Minimal self-hosted RTL operator view (vanilla JavaScript, same-origin APIs, restrictive CSP)

Exit criteria: local app starts predictably, health checks pass, policy-gated task records can be submitted, inspected, cancelled, and processed by an explicitly invoked worker. Provider dispatch is explicit and testable; local Ollama inference is available only after explicit configuration, while the stub performs no inference. Automatic background scheduling, multi-process worker coordination, forced interruption of synchronous handlers, and external side effects remain disabled. Stale recovery uses a five-minute threshold and currently assumes a single local worker process. Retry is restricted to the deterministic `demo.echo` handler; interrupted tasks are never automatically replayed.

## Phase 2 — AI Core and Memory

Architecture proposal: [ADR-0042 — Local-first Knowledge and Memory](../architecture/adr-0042-knowledge-memory.md).

- [x] Separate project knowledge, durable user memory, and operational execution history.
- [x] Define owner, sensitivity, trust, provenance, and retention contracts for the implemented memory and knowledge APIs.
- [x] Add versioned SQLite schema and migration compatibility tests.
- [x] Implement owner-scoped memory CRUD, export, expiry, and deletion.
- [x] Ingest bounded user-supplied Markdown/plain-text documents with source hashes and provenance; supplied URLs are labels only.
- [x] Add SQLite FTS5 indexing and index-consistency/deletion tests.
- [x] Implement owner-scoped FTS5 retrieval with citations and bounded context assembly.
- [x] Add initial prompt-injection and trust-boundary regression coverage.
- [ ] Add source freshness/staleness metadata and repeatable retrieval-quality evaluation.
- [ ] Integrate retrieved context into the model-driven Agent path only after freshness, citation, size-budget, and tool-boundary gates pass.
- [ ] Evaluate embeddings/vector retrieval only if measured FTS5 quality is insufficient.
- [ ] Continue one provider adapter at a time and enforce model/context budget limits.

Exit criteria: a conversation task can retrieve only authorized, in-scope context; every material knowledge result carries verifiable provenance; memory can be exported and deleted; retrieval quality and isolation are covered by repeatable tests. No retrieved document can grant tool permissions or authorize an action.

## Phase 3 — Content and media vertical
- [x] Content brief, draft, review, and approval lifecycle
- [x] Durable scheduled publishing jobs with explicit approval policy and worker-driven dispatch
- [x] Opt-in Telegram text publishing adapter
- [ ] Media-aware Telegram upload and Instagram Graph API publishing adapters
- [x] Owner-scoped local media asset registry and metadata
- [x] Bounded local FFmpeg video-transcoding adapter
- Optional external generation providers
- Retry, deduplication, and failure reporting

Exit criteria: produce a draft and media asset locally; external publishing remains gated and auditable.

## Phase 4 — Agents, workflows, and plugins
- [x] Bounded model-driven orchestration primitive (not yet wired to public API, durable jobs, or context retrieval)
- [ ] Agent registry and bounded delegation
- [x] Durable workflow definitions and step history\n- [ ] Scheduled workflow triggers
- [x] Built-in tool manifests, validation, policy grants, and audit events
- Plugin compatibility and integrity checks
- [x] Durable pause/resume, safe retry, cancellation, checkpoint recovery, and lease fencing\n- [x] Durable owner-authenticated worker emergency-stop and schedule-dispatch pause controls
- [ ] Define and test stop behavior for already-running synchronous and external operations

Exit criteria: a multi-step workflow runs with bounded tools and traceable state transitions. Verified by worker-owned submit/resume paths, separate-process smoke tests, crash-injection recovery, and cancellation regressions.

## Phase 5 — NEXUS and Discovery
- [x] Bounded read-only Python repository inventory and AST analysis foundation
- [ ] Patch proposal and diff review
- Tests executed in an isolated, bounded environment
- Research connectors with source attribution
- Untrusted-content handling and source provenance

Exit criteria: developer/research tasks return reproducible evidence and reviewable changes.

## Phase 6 — Defensive Cybersecurity Lab
- [x] Initial read-only Python static-analysis foundation
- [x] Offline defensive configuration review foundation
- [ ] Broader dependency and configuration auditing
- Authorized asset inventory with explicit scope
- Findings, severity, evidence, and remediation reports
- Safe educational lab mode

Exit criteria: no capability can exceed its declared authorization scope.

## Phase 7 — Packaging and expansion
- Desktop packaging
- Optional Docker deployment
- PostgreSQL migration only if justified
- [x] Local SQLite backup/restore helpers with checksum and integrity verification
- [ ] Target-machine restore drill and protected media/encryption-key backup procedure
- Update health checks and rollback
- Multi-user isolation only after single-user security is established

Exit criteria: a packaged single-user application can be installed, updated, backed up, and rolled back safely.


## Verified implementation snapshot — 2026-11-02

- PR #29 provides the local media asset foundation and bounded FFmpeg processing; social publishing and scheduled delivery are still gated roadmap work.
- PR #30 makes both initial execution and resume execution worker-owned. Resume HTTP requests validate and enqueue only; the pull worker executes under a lease/fencing token.
- PR #31 extends the self-hosted RTL console with Job Engine metrics, owner-scoped Workflow history, step inspection, cancellation, resume-check/enqueue, and manual reconciliation.
- Latest verified CI: PR #31 exact head passed Backend CI and CI on Python 3.11 and 3.12; the Backend suite reported 298 passed.

## Quality gates for every phase
- Formatting and linting
- Unit tests
- Integration tests
- Security regression tests
- Dependency audit
- Manual review of high-impact actions
- Resource usage measured on target hardware
- Documentation and migration notes updated

## First vertical slice
The first implementation slice should be deliberately small: configuration -> API health -> database -> task submission -> mock execution -> status query -> cancellation -> tests. This proves the platform's control plane before introducing real model providers or external side effects.


- [x] Add static model-profile registry with stable IDs and explicit unverified/source labels
- [x] Expose authenticated profile listing and lookup endpoints
- [ ] Replace illustrative estimates with reviewed requirements for exact model/version and quantization before recommending specific models


## Verified implementation snapshot — 2026-11-02 (supersedes earlier snapshot)

- PR #44 made migration version assertions registry-driven.
- PR #45 added local SQLite backup/restore helpers and release-readiness guidance; the actual target-machine restore drill remains unchecked.
- PR #46 added a bounded model-driven orchestration primitive, but not the authenticated public API/worker integration or automatic retrieval-context assembly.
- PR #47 added read-only Python AST analysis; it does not execute source or apply fixes.
- PR #48 added an offline defensive configuration review foundation; it is not a network scanner.
- PR #40 (already merged earlier) added durable worker stop state and authenticated controls. Tests cover preventing new claims while stopped; in-flight external-operation semantics remain an operational gate.
- Next critical gate: integrate retrieval safely into the model-driven Agent path only after source freshness and citation-preserving context-budget evaluation are added.
