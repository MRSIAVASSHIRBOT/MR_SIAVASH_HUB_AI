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
- PR #15 is merged via integration commit `0caa50637800c470b1d52f4ebd2ada78f9196ab8`: it brings worker-owned workflow execution, durable recovery, lease fencing, cancellation handling, worker heartbeat readiness, and the metadata-only capability discovery catalog into `main`. Backend CI and CI passed on integrated head `87438c66f102be5faf62c35391c4dc9cab8a0f3e`, including Python 3.11 and 3.12.
- PR #16 is merged via squash commit `e91c9d51c258292cf995e2b4fbb6b24469d91718`; its initial regression was superseded by a stronger fault-injection test.
- **PR #19 — real external-side-effect crash injection**: merged via squash commit `603b5b141b711cbfbfdaf04bba00969e0078464e`. The test injects an abrupt process crash after the simulated remote action is accepted and before the step result/checkpoint is persisted, then verifies `unknown_outcome` recovery and no automatic replay. Backend CI and CI passed on exact head `6e8b76de633c9776ac7b98022435ffa5d37394ec` (Python 3.11 and 3.12).
- PR #21 is merged via `05cfe315059bbf947278c6c844b75ebbc78caf8a`: a real-process smoke test launches FastAPI and the pull worker separately, enqueues a deterministic workflow over HTTP, and verifies durable success. CI and Backend CI passed on exact head `374295a2441768e9d1b54664990145a1b25f9188`.
- PR #22 is merged via `6cfe5dae7107ebe8754764b6f917fbf848f80e05`: migration 10 adds owner-scoped private memory entries and SQLite FTS5 indexing; authenticated CRUD, lexical search, export, expiry filtering/purge, and metadata-only audit events are implemented. CI and Backend CI passed on exact head `fbccb475e33f94323f27317ba4e547c804f9d8a5`.
- PR #24 is merged via `d879be8a6cf8fc9ed87be2b092a64195dd7c402f`: migration 11 adds owner-scoped source/document/chunk records, bounded text ingestion, SHA-256 provenance, FTS5 retrieval with citation references, export/delete, and a synthetic retrieval evaluation corpus. User-supplied URLs are labels only; no fetching or crawling occurs. CI and Backend CI passed on exact head `2fbc441836afe12f0798b840598a2496cd82823c`.
- PR #25 is merged via `bb7623e1a8da5f848b8a947524e8cc69d8fe6b70`: the optional OpenRouter text adapter is restricted to its approved HTTPS origin, uses bounded requests and sanitized errors, is disabled by default, and has an explicit generation endpoint with no silent fallback. CI and Backend CI passed on exact head `8866bb117e448c6f6a22f6732d2e0eb955d15d41`.
- PR #26 is merged via `6efdab80677338a2fcdae8847f39c5fc6521b337`: the initial self-hosted RTL operator UI exposes status, tasks, provider catalog, memory and knowledge controls, and separate local/remote inference buttons. It uses sessionStorage, a restrictive CSP, no third-party assets, and textContent rendering. CI and Backend CI passed on exact head `cf4c1b726389500c317e20ca48afe28ef396b73f`.
- **PR #29 — local media asset foundation**: merged via `6f90672dc0ea9ad368a68153b3e328fd5df336ea`. Adds owner-scoped local media metadata/storage, bounded upload validation, safe retrieval, fixed-argument FFmpeg video transcoding with resource/time limits, and migration 13. It does not enable social publishing or arbitrary media commands. Backend CI and CI passed on the exact PR head after fixing import order and registering the media router.
- **PR #30 — worker-owned workflow resume**: merged via `fac6d547a731d72f38d50d9bff2f9522343335b7`. Resume requests now validate and enqueue; only the pull worker resumes under its lease/fencing token. Queued and in-flight resume cancellation, final-checkpoint/no-replay behavior, and validation failure are covered. Issue #5 is closed as completed. Backend CI and CI passed on exact head `f3074da24c9adf86a24c36d4a4f2e1e650dbf004`; Backend suite: 297 passed.
- **PR #31 — Job and Workflow operator console**: merged via `bbb95e5c6c67d1741bc95d0c3fa45f8c279487ce`. Adds bounded owner-scoped workflow history, live Job Engine metrics, workflow step inspection, cancellation, resume-check/enqueue, and manual reconciliation of externally verified outcomes. Backend CI and CI passed on exact head `3879bda0d33a8f0e2a7cdc909553b0f328a681e4`; Backend suite: 298 passed.
- Local inference and the optional OpenRouter adapter remain disabled by default unless explicitly configured. Memory and knowledge retrieval are not automatically injected into Agent context. Content drafts and local media foundations exist, but external publishing, scheduling, and external media generation remain roadmap work.

## Live pull-request snapshot

Checked 2026-11-02 (UTC). Re-check live GitHub metadata before making a new merge decision.

- **PR #3 — Phase 4.2 worker-owned workflow execution**: closed without merging; its reviewed implementation is included in PR #15's integrated main commit. A supersession comment explains the disposition.
- **PR #4 — ADR-0042 knowledge/memory architecture**: merged as documentation-only via `ca5bc51871a85bf4c1ad22baed60a1ce84569907`. This is an architecture proposal, not an implementation of memory.
- **PR #6 — workflow dispatch and GitHub capability discovery**: closed without merging. Its original branch diverged from its recorded base (140 ahead / 69 behind) and proposed an alternate submission/dispatch implementation duplicating the architecture now on main. The capability-catalog part is included in PR #15. A comment records why the original branch was closed and requires any genuinely unique future improvements to use a fresh main-based PR.
- **PR #7 — Phase 4.3 cancellation/recovery hardening**: closed without merging; its reviewed implementation is included in PR #15's integrated main commit.
- **PR #10 and PR #13 — project status ledger**: merged. Keep this ledger current through reviewed documentation changes; live metadata remains authoritative.
- **PR #11 and PR #12**: merged. Do not list either as open.
- **PR #14 — standalone capability discovery**: closed without merging because the same reviewed catalog is included in PR #15.
- **PR #15 — Phase 4.2/4.3 worker hardening + capability discovery integration**: merged via `0caa50637800c470b1d52f4ebd2ada78f9196ab8`. Latest-head Backend CI and CI passed on `87438c66f102be5faf62c35391c4dc9cab8a0f3e`.
- **PR #16 — worker crash after external side effect regression test**: merged via `e91c9d51c258292cf995e2b4fbb6b24469d91718`. Backend CI and CI passed on `81bf8868e3869468c00a95988db81cdeb6428e39`.
- **PR #21 — separate-process workflow runtime smoke test**: merged via `05cfe315059bbf947278c6c844b75ebbc78caf8a`. Both CI workflows passed on the exact PR head.
- **PR #22 — owner-scoped memory and FTS5 search**: merged via `6cfe5dae7107ebe8754764b6f917fbf848f80e05`. Both CI workflows passed on the exact PR head.
- **PR #24 — source-backed knowledge ingestion and citation search**: merged via `d879be8a6cf8fc9ed87be2b092a64195dd7c402f`. Both CI workflows passed on the exact PR head.
- **PR #25 — explicit OpenRouter remote text inference**: merged via `bb7623e1a8da5f848b8a947524e8cc69d8fe6b70`. Both CI workflows passed on the exact PR head.
- **PR #26 — self-hosted operator UI**: merged via `6efdab80677338a2fcdae8847f39c5fc6521b337`. Both CI workflows passed on the exact PR head.
- **PR #29 — local media asset foundation**: merged via `6f90672dc0ea9ad368a68153b3e328fd5df336ea`. Both CI workflows passed on the exact PR head after the media router/import correction.
- **PR #30 — worker-owned workflow resume**: merged via `fac6d547a731d72f38d50d9bff2f9522343335b7`. Both CI workflows passed on exact head `f3074da24c9adf86a24c36d4a4f2e1e650dbf004`.
- **PR #31 — Job and Workflow operator console**: merged via `bbb95e5c6c67d1741bc95d0c3fa45f8c279487ce`. Both CI workflows passed on exact head `3879bda0d33a8f0e2a7cdc909553b0f328a681e4`.

## Integration outcomes and remaining risks

- The overlapping worker/recovery/cancellation code from PR #3 and PR #7 is now represented in one main-based integration commit, rather than merging their long feature-branch histories.
- Lease fencing and interrupted external-step recovery are covered by existing regression tests. PR #19 provides the stronger fault-injection case: the worker crashes at the dispatch boundary after a simulated external effect is accepted, then a fresh worker marks the step `unknown_outcome` and does not replay it.
- Capability discovery is metadata-only: it queries public GitHub repository metadata, does not download or execute source code, and never auto-approves candidates. Approval requires explicit license, security, compatibility, and test-plan evidence.
- The original PR #6 worker-dispatch changes were not merged wholesale because they duplicate the current `jobs/workflow_dispatch.py`, `jobs/payload_envelope.py`, and `jobs/idempotency.py` architecture and also conflict on ADR numbering. Any unique improvement needs a fresh, focused PR based on current `main`.
- The memory and source-backed knowledge APIs now support private owner-scoped records, bounded text ingestion, source/chunk provenance, citation-bearing FTS5 retrieval, export/delete, and a synthetic retrieval evaluation corpus. Retrieved content is not automatically inserted into agent prompts; prompt-injection resistance, context assembly, and context-size policy must be evaluated before integration.
- The initial OpenRouter adapter is opt-in and text-only; it is not a general tool-calling or publishing adapter. The self-hosted operator UI is implemented, but deployment hardening is still required before any non-loopback exposure.
- The content/media vertical is partially implemented: owner-scoped content drafts and local media assets/transcoding exist; external social publishing, scheduling, and external generation remain unimplemented.

## Recommended next steps

1. Continue operational readiness work: deployment runbook, backup/restore, worker heartbeat thresholds, and a documented loopback-only default. Do not claim production readiness until a deployment smoke test is performed in the intended environment.
2. Add a synthetic prompt-injection corpus and bounded context assembler for retrieved knowledge. Preserve citations and source trust labels; keep context injection disabled until the evaluation and tool-boundary regressions pass.
3. Extend the content/media vertical with reviewed social-channel adapters and scheduled publishing jobs behind explicit approval, deduplication, and audit controls. Keep external generation optional and disabled by default.
4. Add additional remote providers only when a concrete requirement exists; each must remain opt-in, bounded, cost-aware, and free of silent fallback.
5. Continue with NEXUS read-only analysis and reviewable patches, defensive security, and packaging after these core verticals stabilize.

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
