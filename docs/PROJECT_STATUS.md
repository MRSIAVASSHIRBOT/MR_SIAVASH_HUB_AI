# Project Status Ledger

Last reviewed: 2026-11-02 (UTC)

This file is the durable hand-off point for future development sessions. Re-check live GitHub state before acting; this document is a snapshot, not a substitute for current CI or PR metadata.

## Product definition

MR_SIAVASH_HUB_AI is a local-first, hybrid-capable modular AI workspace. The primary target is one user, with explicit boundaries for later expansion. Existing personal projects (Gshop, game, Telegram bot, and other unrelated repositories) remain separate and must not be modified as part of this project.

The system should discover and evaluate third-party open-source projects, then integrate them through reviewed adapters and bounded interfaces rather than blindly copying code. Prefer free/open-source components, but do not promise that every provider or operation is free. No silent cloud fallback.

## Current baseline on `main`

- FastAPI backend, SQLite persistence and versioned migrations.
- Task/job state, cancellation, policy checks and structured audit events.
- Local owner authentication and action-bound approvals.
- Capability-aware provider contracts, deterministic stub, and opt-in loopback-only Ollama adapter.
- Read-only hardware diagnostics and a conservative model RAM advisor.
- A GitHub Actions OpenCode workflow is present on `main`; PR #11 reports it pinned to a verified action SHA. PR #12 proposes a dedicated free text model endpoint and remains open.
- Remote provider adapters and the minimal React/TypeScript operator UI remain roadmap work.
- Local inference is disabled by default; remote provider calls, shell execution, arbitrary code execution and external publishing are not enabled on the documented baseline.
- Worker architecture on the baseline remains pull-driven and single-process; do not assume the draft workflow branches are part of `main`.

## Open pull requests at review time

- [PR #7 — Phase 4.3: Fenced cancellation, recovery, and worker diagnostics](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_HUB_AI/pull/7): draft, based on `main`. Current reported head is `61dba7b9ed44a477483a31c7d4b0e3d71512dac4`; Backend CI and CI were still in progress when checked. Earlier successful CI for another head is not sufficient. Keep draft until current-head CI and full review pass.
- [PR #6 — Workflow dispatch and GitHub capability discovery](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_HUB_AI/pull/6): draft; based on a feature branch, not directly on `main`; not merge-ready. Crash-window and ambiguous external-outcome fault injection remain.
- [PR #3 — Phase 4.2 worker-owned workflow execution](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_HUB_AI/pull/3): draft on `main`; requires fault-injection coverage for worker termination during an external side effect and lease-expiry races.
- [PR #4 — ADR-0042 knowledge and memory architecture](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_HUB_AI/pull/4): draft, documentation-only proposal; it is not memory implementation.
- [PR #10 — Project status ledger](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_HUB_AI/pull/10): draft documentation handoff; this file lives on its feature branch until merged.
- [PR #12 — Use a dedicated free text model for OpenCode](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_HUB_AI/pull/12): open and not yet merged. Verify the provider endpoint/model is currently available and actually free before relying on it.

PR #11 is listed as closed/merged by the live PR list, but its normalized metadata omitted a merge commit SHA; verify the resulting workflow on `main` before claiming a production smoke test passed.

PR metadata and branch relationships can change; verify them again before any merge or implementation decision.

## Immediate execution order

1. **Harden Phase 4.3 before merging.** Review PR #7 code and tests against the acceptance checklist; wait for current-head CI; add missing regression/fault-injection tests; verify no stale worker can overwrite successor-owned state; verify cancellation does not imply exactly-once execution for arbitrary external effects. Do not merge automatically.
2. **Resolve readiness verification.** The current PR #7 branch contains read-only `/ready` logic and a worker heartbeat implementation, but the hardening checklist still marks the readiness gate incomplete. Add/verify tests for missing schema, stale heartbeat, worker-required mode, and the read-only guarantee; then reconcile checklist and runbook claims.
3. **Reconcile workflow branches.** PR #6 is based on a feature branch, so review dependency order and avoid merging it before its required base is integrated and revalidated. Resolve overlapping changes with PR #3/#7 deliberately.
4. **Implement and verify the first durable worker workflow path** only after crash-window and ambiguous-outcome cases are covered.
5. **Implement Phase 2 memory in small increments:** scoped records, provenance/trust metadata, SQLite FTS5, citation-bearing retrieval, and export/expiry/deletion. Do not ingest arbitrary repositories or write durable user memory automatically without explicit scope and policy.
6. **Implement the smallest operator UI** after stable API contracts are confirmed.
7. **Then build the content/media vertical** with drafts, approval, deduplication and auditable publishing gates; local FFmpeg processing before optional external generators.
8. Continue with NEXUS repository analysis and patch proposals, discovery, defensive cybersecurity, and packaging as defined in the implementation roadmap.

## Definition of done for each code change

- Change is on an isolated branch and linked to a pull request.
- Scope and user-visible behavior are documented.
- Formatting/lint, unit and integration tests, security regressions, and dependency audit are run where applicable.
- Failure and cancellation paths are tested; external side effects are never blindly replayed after an ambiguous outcome.
- CI is green on the latest head, not merely an earlier commit.
- No secrets, tokens, or sensitive execution payloads are committed or logged.
- High-impact actions remain policy-gated and require the configured approval.
- The PR description distinguishes verified behavior from planned work and known limitations.

## Safety and trust boundaries

Only legitimate software development, content creation, and authorized defensive security are in scope. Do not implement credential theft, phishing kits, malware/payload generation, covert tracking, unauthorized access, or evasion. Third-party repositories must be reviewed for license, maintenance, dependency, security, and compatibility before integration.

## Status reporting rule

Never report a feature as complete based only on a plan, PR description, or successful test claim. Confirm the code/branch, latest CI, relevant tests, and actual integration state. Explicitly distinguish `main`, draft PR branches, and future roadmap work.
