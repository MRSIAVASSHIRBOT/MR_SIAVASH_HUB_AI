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

Reviewed 2026-11-02 (UTC). Main now includes the clean integration from PR #15.

- **PR #15 — Phase 4.2/4.3 worker execution + Phase 4.5 capability catalog: MERGED.** Squash commit `0caa50637800c470b1d52f4ebd2ada78f9196ab8`. The exact integration head `87438c66f102be5faf62c35391c4dc9cab8a0f3e` passed Backend CI and CI before merge. Both post-merge workflows also passed on the exact `main` commit `0caa50637800c470b1d52f4ebd2ada78f9196ab8`: Backend CI, including dependency audit, Ruff and tests; CI matrix for Python 3.11 and 3.12, including tests and lint.
- **PR #3 — Phase 4.2 worker-owned workflow execution: CLOSED as superseded.** Its changed paths are included in PR #15's integrated snapshot.
- **PR #7 — Phase 4.3 cancellation/recovery hardening: CLOSED as superseded.** Its changed paths are included in PR #15's integrated snapshot.
- **PR #14 — standalone Phase 4.5 capability catalog: CLOSED as superseded.** All 14 changed paths were included in PR #15.
- **PR #6 — legacy Phase 4.5 workflow dispatch/capability discovery: OPEN, Draft, NOT merge-ready.** Its branch history diverged from the former PR #3 base (recorded comparison: 140 ahead / 69 behind) and it has ten changed paths not present in PR #15. These include an alternative encrypted-input repository, an alternative submission/idempotency repository, an older worker CLI, and associated tests/docs. Do not merge or retarget it. Audit those unique files for requirements or regression tests not already covered by the merged AES-GCM envelope, atomic idempotency repository, worker service, and integration tests; selectively port only verified gaps into a new main-based PR.
- **PR #4 — ADR-0042 memory/knowledge architecture: OPEN, Draft, documentation-only.** It is an architecture proposal, not a memory implementation. Keep it separate from runtime changes until scope and acceptance criteria are settled.

## Confirmed integration and release risks

- The integrated code now exists on `main`; it is no longer correct to describe worker-owned workflow execution, cancellation/recovery hardening, or the metadata-only capability catalog as merely draft-branch work.
- Green CI is evidence that the tested suite passes, not proof of production readiness or arbitrary external-system exactly-once behavior.
- The worker is explicitly pull-driven and must be run as a separate process from the API. Durable workflow submission requires `MRH_WORKFLOW_PAYLOAD_KEY`; there is no plaintext fallback.
- Capability discovery reads public GitHub repository metadata only. It does not fetch, install, import, or execute repository source, and popularity signals never auto-approve a candidate.
- The legacy PR #6 branch is the remaining branch-history hazard. Avoid merging its ancestry; reconcile only specific missing requirements on a fresh branch from `main`.
- The operator UI, real remote model adapters, actual memory/retrieval implementation, and content/media vertical remain roadmap work unless independently verified on `main`.

## Recommended execution order

1. Audit the ten unique paths in PR #6 against the merged implementation and tests. Document each as already covered, useful missing requirement, or obsolete/conflicting implementation.
2. If the audit finds genuine gaps, create a fresh main-based implementation PR containing only those gaps and regression tests; run latest-head CI before merge. Otherwise close PR #6 as superseded with a clear explanation.
3. Run a local operational smoke test in a controlled environment: initialize a fresh database, configure a deployment-specific workflow payload key, start API and worker separately, submit a deterministic workflow, verify completion/cancellation/recovery and inspect that payload ciphertext is removed on terminal outcomes. CI is green, but this real-process check has not yet been observed in this management session.
4. Once the execution/control plane is stable, implement the smallest operator UI against the existing API contracts.
5. Implement memory/retrieval as a separate scoped feature with provenance, owner scope, expiry/deletion controls and citation tests.
6. Add remote model adapters only as explicit opt-in providers with no silent cloud fallback.
7. Build the content/media vertical with draft generation, explicit publishing approval, deduplication and auditable job status; keep external generation providers optional.
8. Continue NEXUS read-only analysis/reviewable patches, defensive security, and packaging after the core user-facing workflow is usable.

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
