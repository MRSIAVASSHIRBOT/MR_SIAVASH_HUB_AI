# Remaining Work Dependency Map

Reviewed against `main` at `e561da2b7641fc4ba78d6e90710998b8fd78b2d1` on 2026-11-03.

This plan defines seven remaining delivery workstreams. They are ordered by dependency and risk, not by visual feature appeal. A workstream is complete only when its acceptance gates are met on the exact proposed commit. Green CI alone is not a production-readiness claim.

## 1. Retrieval safety and Agent context integration

**Existing foundation:** owner-scoped memory and source-backed knowledge APIs, FTS5 retrieval, citation references, and a bounded context assembler.

**Remaining work**
- Build a synthetic prompt-injection corpus covering retrieved documents, hostile instructions, misleading source labels, and conflicting evidence.
- Add explicit source trust/freshness metadata and deterministic context-budget accounting.
- Test owner/scope isolation, stale-source behavior, citation preservation, truncation, and refusal to treat retrieved text as tool authority.
- Integrate context into an actual model-driven orchestration path only after the standalone gates pass.

**Depends on:** existing memory, knowledge, provider router, and policy boundaries.

**Acceptance gate:** reproducible evaluation passes; no retrieved content can grant permissions or bypass policy; every material retrieved claim retains provenance; model-driven integration is covered by end-to-end tests.

## 2. Model-driven Agent Orchestrator

**Existing foundation:** provider registry/router, agent planning and tool validation, workflow execution, context assembly, and audit events.

**Remaining work**
- Implement a bounded model → proposal → policy-check → tool execution → observation loop.
- Enforce per-step and total token/time/tool budgets, maximum turns, cancellation, and deterministic termination.
- Keep model output non-authoritative; each tool call is independently schema-validated and policy-authorized.
- Record redacted decision traces and provider/model identity without logging secrets or private payloads.

**Depends on:** workstream 1 and existing Job/Workflow Engine.

**Acceptance gate:** stub-driven deterministic integration tests plus provider contract tests demonstrate bounded completion, denial handling, cancellation, and no unapproved tool execution.

## 3. Complete the content/media publishing vertical

**Existing foundation:** owner-scoped drafts and revisions, explicit approval, durable schedules, worker dispatch, local media storage/transcoding, and opt-in Telegram text publishing.

**Remaining work**
- Add media-aware Telegram publishing only with size/type limits and tested upload handling.
- Implement Instagram only after professional-account Graph API configuration and a secure, externally reachable media delivery design exist.
- Add provider-specific reconciliation for ambiguous outcomes, schedule deduplication, and operator-visible failure states.
- Keep generated media providers optional and approval-gated.

**Depends on:** existing asset store, schedule dispatcher, approval policy, and secret configuration.

**Acceptance gate:** mocked provider tests cover success, permanent rejection, rate limits, ambiguous outcomes, duplicate prevention, approval revocation, and media validation. Real account acceptance remains a separate manual deployment check.

## 4. Workflow operations and emergency-stop control

**Existing foundation:** durable jobs/workflows, lease fencing, cancellation, safe resume, recovery, heartbeat readiness, and operator reconciliation.

**Remaining work**
- Add an explicit emergency-stop state that prevents new dispatch and blocks resumption until an owner clears it.
- Define behavior for in-flight synchronous handlers and external operations already submitted.
- Add race tests for stop-vs-claim, stop-vs-resume, stop-vs-retry, and stale worker lease ownership.
- Document recovery and operator procedures.

**Depends on:** Job/Workflow Engine and operator console.

**Acceptance gate:** deterministic concurrency tests prove no new work is claimed while stopped; in-flight external effects are never blindly replayed; only an authenticated owner can clear the stop.

## 5. NEXUS Developer Agent (read-only first)

**Remaining work**
- Build repository inventory and static read-only analysis over explicitly selected repositories/directories.
- Produce findings with file/line evidence, confidence, and remediation suggestions.
- [x] Add review-only patch proposals with syntax checks, AST risk deltas, confidence, line evidence, and remediation guidance; never apply automatically.
- Run tests only in an isolated, resource-bounded environment after an explicit user action.

**Depends on:** Agent Orchestrator, capability registry, audit trail, and safe file access.

**Acceptance gate:** tests prove repository scope enforcement, no implicit network access, no arbitrary shell execution, reproducible findings, and review-before-write.

## 6. Defensive Cybersecurity Lab

**Remaining work**
- [x] Add authenticated offline configuration review with exact asset matching, expiring authorization (maximum 30 days), file/line evidence, confidence, and remediation guidance.
- [x] Add offline requirements-manifest inventory for unpinned, direct/VCS, nested-include, and custom-index entries; never install or resolve packages.
- [x] Record only metadata-only audit events; do not log configuration or manifest contents.
- [ ] Add a vulnerability-database review using an explicitly approved advisory snapshot; no implicit network access.
- [ ] Add log analysis and authorized asset inventory as separate, scope-bound offline capabilities.
- Keep exploit deployment, credential collection, stealth, evasion, and malware/payload generation out of scope.

**Depends on:** policy engine, audit service, bounded tools, and NEXUS read-only analysis.

**Acceptance gate:** scope-boundary and authorization tests demonstrate that no scan or analysis can exceed the declared permitted assets; findings are reproducible and evidence-linked.

## 7. Packaging, backup/restore, and release readiness

**Remaining work**
- Define a supported local installation and upgrade path for the target Windows environment.
- Add backup/restore procedures covering SQLite, media assets, and the workflow encryption key as separate protected material.
- Add restore drills, migration checks, rollback guidance, and health checks.
- Measure resource use on the actual target laptop; do not infer local-model compatibility from generic estimates.
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
