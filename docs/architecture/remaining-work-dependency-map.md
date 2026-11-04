# Remaining Work Dependency Map

Reviewed against `main` at `3134fb50d47f7ab87934971a27e2ba90c85263d8` on 2026-11-04.

This plan defines seven remaining delivery workstreams. They are ordered by dependency and risk, not by visual feature appeal. A workstream is complete only when its acceptance gates are met on the exact proposed commit. Green CI alone is not a production-readiness claim.

## 1. Retrieval safety and Agent context integration

**Existing foundation:** owner-scoped memory and source-backed knowledge APIs, FTS5 retrieval, citation references, bounded context assembly, owner-declared freshness metadata, source/chunk integrity checks, repeatable synthetic retrieval metrics, and context integration into both synchronous `POST /agent/run` and queued `POST /agent/model-runs`. Retrieved passages are carried as untrusted evidence; they do not grant tool authority.

**Remaining work**
- Add independent publisher/source-content verification beyond local hashes and owner-declared freshness labels.
- Expand prompt-injection and conflicting-evidence evaluations with a representative corpus, not only synthetic fixtures.
- Keep deterministic context-budget, owner-isolation, stale-source, citation-preservation, truncation, and policy-separation regressions across both synchronous and durable Agent paths.
- Evaluate vector retrieval only if measured FTS5 quality is insufficient.

**Depends on:** existing memory, knowledge, provider router, and policy boundaries.

**Acceptance gate:** reproducible evaluation passes; no retrieved content can grant permissions or bypass policy; every material retrieved claim retains provenance; model-driven integration is covered by end-to-end tests.

## 2. Model-driven Agent Orchestrator

**Existing foundation:** bounded `AgentOrchestrator` model → proposal → policy-checked tool → observation loop; strict proposal schemas; registered specialist delegation; server-side ToolRegistry validation and policy checks; bounded turns, runtime, input size, tool calls and delegations; retrieved context treated as untrusted; and worker-owned durable model-run submission with encrypted request/result storage.

**Remaining work**
- Define durable per-turn checkpoints only if resumability is required; the current model/tool loop is intentionally one non-replayable workflow step.
- Strengthen failure-injection tests around cancellation and lease loss during provider calls and external tool effects. Synchronous provider calls cannot be forcibly interrupted; late results must not dispatch new tools.
- Keep decision traces redacted and preserve provider/model identity without logging secrets or private payloads.
- Expand representative integration tests for tool denial, approval-required outcomes, budget exhaustion, delegation, cancellation and unknown outcomes.

**Depends on:** workstream 1 and existing Job/Workflow Engine.

**Acceptance gate:** stub-driven deterministic integration tests plus provider contract tests demonstrate bounded completion, denial handling, cancellation, and no unapproved tool execution.

## 3. Complete the content/media publishing vertical

**Existing foundation:** owner-scoped drafts/revisions, explicit approval, durable schedules and worker dispatch; opt-in Telegram text and photo/video media adapters; opt-in Instagram Graph API image publishing; signed public-media URL generation; owner-scoped media storage; bounded FFmpeg processing and local rendering.

**Remaining work**
- Complete public HTTPS media-origin configuration, edge controls, Graph API scopes/credentials, and a controlled real-account acceptance test.
- Add/verify provider-specific reconciliation for ambiguous social-publishing outcomes, schedule deduplication and operator-visible failure states.
- Connect versioned editable timeline drafts to immutable render-job snapshots; currently the render route consumes the original analysis timeline, not the edited draft.
- Keep external generation providers optional, reviewed, disabled by default and approval-gated; no video-generation adapter is currently registered.

**Depends on:** existing asset store, schedule dispatcher, approval policy, and secret configuration.

**Acceptance gate:** mocked provider tests cover success, permanent rejection, rate limits, ambiguous outcomes, duplicate prevention, approval revocation, and media validation. Real account acceptance remains a separate manual deployment check.

## 4. Workflow operations and emergency-stop control

**Existing foundation:** durable jobs/workflows, lease fencing, cancellation, safe resume, stale recovery, heartbeat readiness, authenticated emergency-stop and schedule-pause controls, and operator reconciliation. Current stop controls prevent new claims/dispatch.

**Remaining work**
- Define and test behavior for in-flight synchronous handlers and external operations already submitted; stop is not a claim that arbitrary provider calls can be forcibly interrupted.
- Add race tests for stop-vs-claim, stop-vs-resume, stop-vs-retry and stale worker ownership.
- Document operator recovery procedures and verify them in a separate-process deployment drill.

**Depends on:** Job/Workflow Engine and operator console.

**Acceptance gate:** deterministic concurrency tests prove no new work is claimed while stopped; in-flight external effects are never blindly replayed; only an authenticated owner can clear the stop.

## 5. NEXUS Developer Agent (read-only first)

**Existing foundation:** bounded read-only Python repository inventory and AST analysis, alias-aware import/shell API checks, evidence-linked findings, and review-only patch proposals with syntax checks, AST risk deltas and remediation guidance. No target code is executed and patches are not auto-applied.

**Remaining work**
- Run proposed tests only after explicit user action in an isolated, resource-bounded environment.
- Broaden language/dependency coverage and validate performance on larger repositories.
- Keep repository scope explicit and prohibit implicit network access or arbitrary shell execution.

**Depends on:** Agent Orchestrator, capability registry, audit trail, and safe file access.

**Acceptance gate:** tests prove repository scope enforcement, no implicit network access, no arbitrary shell execution, reproducible findings, and review-before-write.

## 6. Defensive Cybersecurity Lab

**Existing foundation:** authenticated offline configuration review with exact asset matching, expiring authorization, file/line evidence, confidence and remediation; offline requirements-manifest inventory without installation or network resolution; and metadata-only audit events.

**Remaining work**
- Add vulnerability-database review using an explicitly approved advisory snapshot; no implicit network access.
- Add log analysis and authorized asset inventory as separate, scope-bound defensive capabilities.
- Add reproducible finding evidence and remediation reports; keep all operations non-destructive and within the declared authorization scope.
- Keep exploit deployment, credential collection, stealth, evasion, and malware/payload generation out of scope.

**Depends on:** policy engine, audit service, bounded tools, and NEXUS read-only analysis.

**Acceptance gate:** scope-boundary and authorization tests demonstrate that no scan or analysis can exceed the declared permitted assets; findings are reproducible and evidence-linked.

## 7. Packaging, backup/restore, and release readiness

**Existing foundation:** SQLite backup/restore helpers with checksum and integrity verification, media integrity verification, versioned migrations, Windows local launcher scripts, packaged UI verification in CI, and release-readiness runbooks.

**Remaining work**
- Demonstrate a target-machine restore drill covering SQLite, media assets and the separately protected workflow encryption key.
- Complete a clean Windows install/upgrade/rollback and health-check acceptance run.
- Measure resource use on the actual target laptop; do not infer local-model compatibility from generic estimates.
- Define dependency locking, license selection, release version/tag policy and owner-approved publication.
- Keep loopback-only networking as the default; multi-worker or public deployment requires shared rate limiting, trusted-proxy configuration, and separate security review.

**Depends on:** stable core services and completed operational runbooks.

**Acceptance gate:** clean install, upgrade, backup, restore, and rollback are demonstrated in a clean environment; restored encrypted workflows are readable with the matching key; no secret is stored in the repository.

## Cross-cutting delivery rules

- Work only in `MRSIAVASSHIRBOT/MR_SIAVASH_HUB_AI`; unrelated repositories remain out of scope.
- Use isolated, focused branches and PRs; do not force-push or delete branches as a shortcut.
- Never bypass branch protection or merge a failing check.
- Keep external providers disabled unless explicitly configured; never silently fall back.
- Treat model output, retrieved documents, web pages, and plugin responses as untrusted data.
- Every high-impact operation remains policy-gated and requires explicit approval.
- Report implementation, CI verification, target-environment validation, and production readiness as separate states.
