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
- Remote provider adapters and the minimal React/TypeScript operator UI remain roadmap work.
- Local inference is disabled by default; remote provider calls, shell execution, arbitrary code execution and external publishing are not enabled on the documented baseline.
- Worker architecture on the baseline remains pull-driven and single-process; do not assume the draft workflow branches are part of `main`.

## Open pull requests at review time

- [PR #7 — Phase 4.3: Fenced cancellation, recovery, and worker diagnostics](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_HUB_AI/pull/7): draft, based on `main`. Latest-head Backend CI and CI were reported successful for head `1142d74f0a0232e526634bf2061ac4c0cff3bb4f`. Keep draft until the full code/security review and acceptance checklist are complete.
- [PR #6 — Workflow dispatch and GitHub capability discovery](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_HUB_AI/pull/6): draft; based on a feature branch, not directly on `main`; not merge-ready. Crash-window and ambiguous external-outcome fault injection remain.
- [PR #3 — Phase 4.2 worker-owned workflow execution](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_HUB_AI/pull/3): draft on `main`; requires fault-injection coverage for worker termination during an external side effect and lease-expiry races.
- [PR #4 — ADR-0042 knowledge and memory architecture](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_HUB_AI/pull/4): draft, documentation-only proposal; it is not memory implementation.

PR metadata and branch relationships can change; verify them again before any merge or implementation decision.

## Immediate execution order

1. **Harden Phase 4.3 before merging.** Review PR #7 code and tests against the acceptance checklist; inspect latest CI on the current head; add missing regression/fault-injection tests; verify no stale worker can overwrite successor-owned state; verify cancellation does not imply exactly-once execution for arbitrary external effects. Do not merge automatically.
2. **Reconcile workflow branches.** PR #6 is based on a feature branch, so review dependency order and avoid merging it before its required base is integrated and revalidated. Resolve overlapping changes with PR #3/#7 deliberately.
3. **Implement and verify the first durable worker workflow path** only after crash-window and ambiguous-outcome cases are covered.
4. **Implement Phase 2 memory in small increments:** scoped records, provenance/trust metadata, SQLite FTS5, citation-bearing retrieval, and export/expiry/deletion. Do not ingest arbitrary repositories or write durable user memory automatically without explicit scope and policy.
5. **Implement the smallest operator UI** after stable API contracts are confirmed.
6. **Then build the content/media vertical** with drafts, approval, deduplication and auditable publishing gates; local FFmpeg processing before optional external generators.
7. Continue with NEXUS repository analysis and patch proposals, discovery, defensive cybersecurity, and packaging as defined in the implementation roadmap.

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
