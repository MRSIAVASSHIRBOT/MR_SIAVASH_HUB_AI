# Project Status Ledger

Last reviewed: 2026-11-02 (UTC)

This is a live hand-off snapshot. Re-check GitHub metadata and latest-head CI before every merge or implementation decision.

## Product definition

MR_SIAVASH_HUB_AI is a local-first, hybrid-capable modular AI workspace for one primary user. Discover and evaluate third-party open-source projects, then integrate them through reviewed adapters and bounded interfaces; do not blindly copy repositories. Prefer free/open-source components without promising every provider or operation is free. No silent cloud fallback.

Unrelated repositories (Gshop, the game, Telegram bot, and others) must remain out of scope.

## Main baseline and merged hardening

- Main contains the FastAPI/SQLite control-plane baseline, task/job state, cancellation, policy checks, structured audit events, local owner authentication, action-bound approvals, capability-aware model routing, deterministic stub, and opt-in loopback-only Ollama adapter.
- PR #11 is merged: the OpenCode action is pinned to a specific commit SHA and its prompt requires verified reporting.
- PR #12 is merged: OpenCode uses the explicit `openrouter/cohere/north-mini-code:free` model identifier. Availability and actual zero-cost operation remain provider-dependent; do not assume this endpoint is permanently available or free.
- Local inference remains disabled by default. Do not claim the draft worker/workflow branches are already part of main.
- The operator UI, real remote provider adapters, memory implementation, and content/media vertical remain roadmap work unless separately verified on main.

## Live pull-request snapshot

Checked 2026-11-02 (UTC). Draft status is intentional; green CI alone does not mean a PR is merge-ready.

- **PR #3 — Phase 4.2 worker-owned workflow execution**: open, Draft, based on main. Head `ca1b40f27201f7d353d8ee82ee760019126eb231`. Backend CI and CI workflow runs were completed successfully for this head. Still requires explicit fault-injection coverage for worker termination during an external side effect and lease-expiry races before merge.
- **PR #4 — ADR-0042 knowledge/memory architecture**: open, Draft, documentation-only. Head `2dea4730191d3d396e2f89a9e90649950f3c5386`. Backend CI completed successfully. This is an architecture proposal, not an implementation of memory.
- **PR #6 — workflow dispatch and GitHub capability discovery**: open, Draft, based on `feat/phase-4-2-unified-job-recovery`. Head `3b2c5a2e68bd6741f0a2a419e83cc7a9405c0e36`. Its recorded base SHA is `68ea8fa5af009d7a9cfded116fe279dd3db0ed82`; live comparison of the base/head refs reports `diverged`, 140 commits ahead and 69 behind, with that SHA as merge base. PR #3 currently has a newer head (`ca1b40f27201f7d353d8ee82ee760019126eb231`). No PR-triggered workflow runs were returned for PR #6's current head. PR #6 is not mergeable and must not be retargeted or merged until the branch history is reconciled and CI passes on the resulting head.
- **PR #7 — Phase 4.3 cancellation/recovery hardening**: open, Draft, based on main. Latest reviewed head `6ed6bcc5d439189107ac66f3a5b35af24085c3a2` adds a regression test rejecting stale worker heartbeats and updates the hardening checklist. Backend CI and CI both completed successfully on this exact head, including Python 3.11 and 3.12. The release gate remains open because branch-overlap and broader cancellation/recovery review are still required. Keep Draft until latest-head CI, readiness behavior, cancellation/recovery crash windows, and the acceptance checklist/runbook are reconciled and reviewed.
- **PR #10 — this project status ledger**: merged into `main` via squash commit `1ae9afe09ed231c0a2b3327f5b0fd7d810e0d982` after the latest-head Backend CI passed. Keep this ledger updated through reviewed documentation PRs; do not treat it as a substitute for live metadata.
- **PR #11**: merged. **PR #12**: merged. Do not list either as open.

## Confirmed file-overlap and dependency risks

Changed-file lists were compared live:

- PR #3 and PR #7 share **40 paths**, including workflow execution, persistence/migrations, worker, API routes, security, README, and tests. They must be reconciled deliberately; do not merge both based only on independent green CI.
- PR #3 and PR #6 share **15 paths**.
- PR #6 and PR #7 share **16 paths**.
- PR #6 targets the PR #3 feature branch as its base, but the recorded base SHA is older than PR #3's current head and the refs have diverged. This is a history-reconciliation blocker, not merely a merge-order choice.
- PR #4 and PR #6 both touch `docs/roadmap/implementation-plan.md`; resolve the documentation overlap if both changes are retained.
- PR #10 is documentation-only and does not resolve implementation branch conflicts.

A clean GitHub mergeability flag does not prove logical compatibility. Run integration tests after every dependency-aware merge.

## Recommended execution order

1. Keep implementation PRs in Draft while completing review. Do not merge PR #6 or change its base yet: reconcile the divergent branch history against PR #3 first, then rerun CI on the resulting head.
2. Review PR #7's latest-head implementation and tests against the readiness/cancellation acceptance checklist. Verify read-only readiness with absent/unmigrated schema, missing/stale heartbeat, and worker-required mode. Verify stale workers cannot overwrite successor-owned state and uncertain external outcomes are not blindly replayed.
3. Review PR #3's encrypted payload, worker lifecycle, idempotency, lease handling, and crash-window tests. Add fault-injection tests for worker termination during external side effects and lease expiry before considering merge.
4. Reconcile PR #3 and PR #7 overlapping paths on a controlled integration branch or by updating one feature branch at a time; rerun all CI on the final rebased head. Preserve explicit user approval and audit boundaries.
5. Rebase/reconcile PR #6 only after its required base is settled. Resolve the 15/16 overlapping paths and run CI on its new head; add crash-window and ambiguous-external-outcome tests.
6. Keep PR #4 as a documentation decision until a separate, scoped implementation PR adds memory: scoped records, provenance/trust metadata, SQLite FTS5 retrieval, citations, and export/expiry/deletion controls. No broad repository ingestion or automatic durable-memory writes without explicit scope and policy.
7. Implement the smallest operator UI only after API contracts stabilize.
8. Then implement the content/media vertical with drafts, approval, deduplication, auditability, and local FFmpeg processing before optional external generators. Continue with NEXUS read-only analysis and reviewable patches, defensive security, and packaging afterward.

## Definition of done for each code change

- Isolated branch and linked PR with a narrow, explicit scope.
- Formatting/lint, unit/integration tests, relevant security regressions, and dependency audit run as applicable.
- Latest-head CI is green; an earlier successful commit is insufficient.
- Failure/cancellation paths are tested; ambiguous external effects are not blindly replayed.
- No secrets, tokens, or sensitive execution payloads are committed or logged.
- High-impact actions remain policy-gated and require configured approval.
- PR text distinguishes verified behavior, limitations, and planned work.

## Safety and trust boundaries

Only legitimate software development, content creation, and authorized defensive security are in scope. Do not implement credential theft, phishing kits, malware/payload generation, covert tracking, unauthorized access, or evasion. Review license, maintenance, dependency, security, and compatibility before integrating third-party code.

## Status reporting rule

Never report a feature complete based only on a plan, PR description, or successful test claim. Verify code/branch, latest CI, relevant tests, and actual integration state. Always distinguish main, draft PR branches, and roadmap work.
