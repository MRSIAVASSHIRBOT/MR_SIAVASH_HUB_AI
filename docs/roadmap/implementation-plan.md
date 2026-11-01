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
- [ ] Real remote provider adapter (separate opt-in milestone; explicit secrets and network policy required)
- [ ] Minimal React/TypeScript operator view

Exit criteria: local app starts predictably, health checks pass, policy-gated task records can be submitted, inspected, cancelled, and processed by an explicitly invoked worker. Provider dispatch is explicit and testable; local Ollama inference is available only after explicit configuration, while the stub performs no inference. Automatic background scheduling, multi-process worker coordination, forced interruption of synchronous handlers, and external side effects remain disabled. Stale recovery uses a five-minute threshold and currently assumes a single local worker process. Retry is restricted to the deterministic `demo.echo` handler; interrupted tasks are never automatically replayed.

## Phase 2 — AI Core and Memory
- One provider adapter at a time
- Capability-aware model routing
- Context budget management
- Explicit memory scopes and provenance
- SQLite FTS search before vector database adoption
- Data export and deletion controls

Exit criteria: a conversation task can retrieve only authorized context and explain which sources were used.

## Phase 3 — Content and media vertical
- Content brief, draft, review, and approval lifecycle
- Social channel adapters behind the publishing service
- Scheduled publishing jobs with explicit approval policy
- Media asset registry
- FFmpeg-based local processing adapter
- Optional external generation providers
- Retry, deduplication, and failure reporting

Exit criteria: produce a draft and media asset locally; external publishing remains gated and auditable.

## Phase 4 — Agents, workflows, and plugins
- Agent registry and bounded delegation
- Workflow definitions and schedules
- Tool manifests, validation, grants, and audit
- Plugin compatibility and integrity checks
- Pause/resume/retry and emergency stop

Exit criteria: a multi-step workflow runs with bounded tools and traceable state transitions.

## Phase 5 — NEXUS and Discovery
- [x] Add persistent metadata-only capability source catalog with canonical HTTPS URLs
- [x] Add authenticated candidate listing and review-state endpoints
- [x] Require license, security, compatibility, and test-plan evidence before marking a source approved
- [ ] Add automated GitHub repository metadata/license/release inspection without executing source code
- [ ] Add isolated compatibility and security evaluation jobs with bounded resources
- [ ] Add reviewed connector/skill adapters and an explicit activation/rollback workflow
- Repository-aware read-only analysis first
- Patch proposal and diff review
- Tests executed in an isolated, bounded environment
- Research connectors with source attribution
- Untrusted-content handling and source provenance

Exit criteria: developer/research tasks return reproducible evidence and reviewable changes.

## Phase 6 — Defensive Cybersecurity Lab
- Static analysis
- Dependency and configuration auditing
- Authorized asset inventory with explicit scope
- Findings, severity, evidence, and remediation reports
- Safe educational lab mode

Exit criteria: no capability can exceed its declared authorization scope.

## Phase 7 — Packaging and expansion
- Desktop packaging
- Optional Docker deployment
- PostgreSQL migration only if justified
- Backup/restore verification
- Update health checks and rollback
- Multi-user isolation only after single-user security is established

Exit criteria: a packaged single-user application can be installed, updated, backed up, and rolled back safely.

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
