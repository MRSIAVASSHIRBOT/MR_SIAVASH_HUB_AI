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


## Superseding live snapshot — 2026-11-02

This section supersedes any earlier statements in this ledger that conflict with the merged main head below. The current main commit at the time of review is `d2e4689dcdc873391ca4820dfaba60fba6298cbf`.

### Newly integrated milestones

- **PR #32 — status/roadmap synchronization**: merged.
- **PR #33 — bounded memory and knowledge context assembly**: merged. The assembler is present, but this does not by itself establish a fully model-driven agent reasoning loop or prove that every agent path consumes retrieved context.
- **PR #34 — durable approval-gated content scheduling**: merged. Schedule records and approval/version binding are implemented.
- **PR #35 — worker-driven schedule dispatch**: merged. Dispatch is pull-driven through the worker; it does not create an always-on scheduler at API startup.
- **PR #36 — configurable Telegram publishing adapter**: merged. Telegram text publishing is opt-in through environment configuration and an explicit worker cycle. Telegram does not provide a provider idempotency key for `sendMessage`; ambiguous outcomes are quarantined rather than blindly retried.
- Instagram publishing remains unavailable: it requires the professional-account Graph API path, credentials, and a publicly reachable media URL. The local media asset endpoint is not a substitute for a public media URL.

### Exact-head CI evidence

On `d2e4689dcdc873391ca4820dfaba60fba6298cbf`, both latest push workflows completed successfully:
- Backend CI: run [41374734670](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_HUB_AI/actions/runs/41374734670)
- CI: run [41374734542](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_HUB_AI/actions/runs/41374734542)

These results verify the configured CI jobs on this commit; they do not replace target-device runtime, backup/restore, or real provider-account acceptance tests.

### Current product boundaries

- The memory/knowledge context assembler is implemented, but retrieval evaluation, prompt-injection regression coverage, and safe integration into a true model-driven agent loop remain explicit gates.
- The content path now includes drafts, approval, durable schedules, worker dispatch, and an opt-in Telegram text adapter. Instagram, media publication, and external generation are not complete.
- The workflow engine is durable and worker-owned, but a production-grade emergency stop and multi-worker deployment approval remain open.
- The operator UI exists; production exposure, backup/restore verification, packaging, and target-device resource measurements remain open.

See [remaining-work-dependency-map.md](architecture/remaining-work-dependency-map.md) for the seven remaining workstreams, their prerequisites, and acceptance gates.


## Superseding integration snapshot — 2026-11-02 UTC

This snapshot supersedes earlier roadmap/status statements that conflict with the merged PRs listed here. Review baseline immediately before this documentation update: main contained `e0166007ea42dafa1ef780d9094c0d3b1baf79b4`. CI on that pre-documentation head was still running when checked; do not treat it as a completed check result.

### Newly merged milestones

- **PR #44 — registry-driven migration expectations**: merged as `71d5a347a49643e6ad64cd3f57d13b5dd1bf14f5`. Migration tests now derive expected versions from `MIGRATIONS`, avoiding hard-coded version lists when new migrations are added.
- **PR #45 — verified local SQLite backup/restore**: merged as `5552286b28edc5fb2fbc484a5e057e8d70febf95`. Adds SQLite online backup, SHA-256/size manifest validation, SQLite quick-check, no-overwrite destination publication, tests, and a release-readiness checklist. This backs up SQLite only; media files, provider secrets, and workflow encryption keys remain separate.
- **PR #46 — bounded model-driven Agent orchestration primitive**: merged as `1576a6204158a62dd19a085b717fc8199275d9d5`. Adds a finite model/proposal/tool/observation loop with strict proposal schema, turn/input/tool/output limits, cancellation checks, and independent server-side registry policy checks. It is not yet connected to the public API, durable worker jobs, or the context assembler; this is a primitive, not a complete autonomous agent.
- **PR #47 — NEXUS read-only Python static analysis**: merged as `0bdaee649d1a469d2e09397686392068c2599db9`. Adds bounded repository inventory and AST checks with file/line/rule evidence; analyzed code is not imported or executed and no files are modified. Findings are advisory and the rule set is intentionally narrow.
- **PR #48 — offline defensive configuration review**: merged as `e0166007ea42dafa1ef780d9094c0d3b1baf79b4`. Adds explicit scope/expiry validation and bounded checks for selected risky configuration patterns. It is a local/offline review foundation, not an active scanner or comprehensive security audit.

### Current verified boundaries

- Worker emergency-stop state is implemented and prevents new worker claims while stopped; stop semantics for already-running synchronous/external operations still need explicit operational treatment.
- Memory/knowledge context assembly and initial prompt-injection boundary regression tests exist. Source freshness and retrieval-quality evaluation remain incomplete, and the new Agent loop does not yet consume retrieved context through an end-to-end model-facing path.
- Drafts, explicit approval, durable content schedules, worker-driven dispatch, local media storage/transcoding, and opt-in Telegram text publishing exist. Media-aware Telegram publishing and Instagram Graph API publishing remain incomplete.
- Backup/restore code has CI coverage, but a restore drill on the target machine and protected backup procedures for media/key material have not been performed here.
- NEXUS static analysis and offline configuration review are foundations only. Reviewable patch proposals, dependency auditing, target-device packaging, and clean install/upgrade/rollback drills remain open.

### Recommended next delivery order

1. Finish retrieval freshness, citation-preserving context budgets, and end-to-end safety tests before connecting retrieved context to the model loop.
2. Integrate the bounded Agent loop through an authenticated, bounded execution path with auditable provider selection and explicit cancellation/timeout behavior.
3. Complete media-aware Telegram publishing with upload/size/type validation and ambiguous-outcome handling; separately design Instagram's professional Graph API and publicly reachable media delivery.
4. Verify backup/restore, encrypted workflow recovery, migrations, clean installation, and rollback on the intended Windows machine.
5. Extend NEXUS and defensive review with reviewable patch proposals, dependency/configuration coverage, and stronger scope/evidence tests.

A green CI result is not equivalent to target-machine validation or production readiness.


## Superseding integration snapshot — 2026-11-02 UTC

This snapshot supersedes the earlier snapshot above where it describes the Agent API or Telegram media publishing as incomplete. Baseline immediately before this documentation update: `efee3a5ac0f6adec5a869f4550ab2339d879cf5e`.

### Newly merged milestones

- **PR #50 — owner-declared source freshness**: merged. Knowledge sources default to `unknown`; an authenticated owner can mark them `owner_reviewed_current` or `stale`. Search results and Agent context preserve the label and review timestamp. This is not automatic URL verification.
- **PR #51 — authenticated bounded Agent run**: merged. `POST /agent/run` assembles owner-scoped memory/knowledge context, passes passages as untrusted evidence, and returns source references separately from the answer. It requires explicit local or remote provider mode, excludes the stub provider, and audits metadata without logging the goal/context/answer.
- **PR #52 — Agent provider timeout cap**: merged. The synchronous endpoint caps each provider call at 30 seconds and allows at most three turns. Worst-case provider wait is roughly 90 seconds plus local processing overhead; this is not a durable long-running workflow.
- **PR #53 — approved Telegram media publishing**: merged. Draft revisions bind owner-scoped JPEG/PNG/MP4 assets; attachment changes reset approval. The worker resolves and validates the local file immediately before dispatch. The adapter uploads via Telegram `sendPhoto`/`sendVideo`, checks caption/file bounds, and preserves ambiguous-outcome handling.
- **PR #54 — operator media library**: merged. The authenticated local dashboard can upload/list/delete media and attach assets to Telegram drafts. Deletion conflicts are surfaced rather than bypassed.
- **PR #55 — Agent run UI**: merged. The dashboard exposes the bounded Agent endpoint, explicit local/remote mode, memory/knowledge inclusion, turn/output caps, and source trust/freshness metadata.

### Current implementation boundaries

- The Agent endpoint is synchronous and exposes only the deterministic `text.echo` tool. It is not yet a durable worker-owned Agent job or multi-agent delegation system.
- Telegram media publishing requires an approved draft, configured Bot API credentials, a functioning worker cycle, and an available local asset. The code/tests use mocked HTTP; no real Telegram post was performed here.
- Instagram Graph API publishing is still incomplete. It requires professional-account/app credentials and a publicly reachable media delivery path; local file paths alone are insufficient. Do not put tokens in source code or chat.
- Freshness status is owner-declared, not independently verified. Retrieval-quality evaluation and stronger freshness checks remain open.
- Backup/restore helpers exist, but a target-machine restore drill and protected backup for media/encryption-key material remain open.
- NEXUS static analysis and offline configuration review are advisory foundations. Patch proposals, dependency auditing, and target-machine install/upgrade/rollback validation remain open.

### Next priorities

1. Add repeatable retrieval-quality and stale-source handling evaluation before broadening Agent tools.
2. Move longer Agent work to durable worker-owned jobs with persisted state, cancellation, and recovery.
3. Finish Instagram's external integration only after public media hosting and credentials are configured outside the repository.
4. Perform a real target-machine backup/restore and clean install/rollback drill.
5. Expand NEXUS findings and defensive configuration coverage with evidence-backed tests.

A green CI result is not a substitute for live provider or target-machine validation.


## Release-readiness update — 2026-11-02 UTC

This section supersedes earlier statements above where they conflict with the following merged changes. Latest relevant merged heads:
- PR #74 merged as `294329da3afb043350b22f9e4b3214456c7bf67a`; CI and Backend CI passed on PR head `78fe761f8b7c7790a99b3d1fbb07d6d0ff15d223` (Python 3.11 and 3.12 for CI). It replaces a broad exception assertion with exact HTTP 503 and stable error-detail checks for missing signed-media configuration.
- PR #75 merged as `4d83a4c59a4a688caff5fcd2fb42a34909edf14c`; CI and Backend CI passed on PR head `1b4ca24f4b4df5d1b1355add8f558c8d67dd77d8`. Public signed media delivery now verifies JPEG/PNG file signatures against stored media types before serving bytes and has mismatch regression coverage.

### Six workstreams — implementation vs. release gates

1. **Instagram/media delivery — code foundation integrated.** The dispatcher generates short-lived signed HTTPS media URLs for approved JPEG/PNG Instagram schedules. The public route binds asset UUID and expiry with HMAC, limits URLs to 15 minutes, validates media type and bytes, and fails closed when configuration is absent. Still blocked on externally verified HTTPS reachability, edge rate limiting/query-string log hygiene, authorized professional-account credentials, and a controlled end-to-end publish/reconciliation test. No live Instagram post has been performed by CI.
2. **Workflow operations/emergency stop — core behavior and regression coverage exist.** The durable stop flag blocks new worker claims and remains latched until an explicit resume. Tests cover an in-flight synchronous handler, preventing the next claim, and resuming after the stop. The stop does not magically cancel an already-running external side effect; multi-process deployment behavior and operator procedures still require target-environment validation.
3. **Retrieval and Agent context safety — bounded integration exists.** Memory and knowledge evidence are owner-scoped, carry provenance/trust/freshness labels, are bounded by per-item and total character limits, and are explicitly marked untrusted. The authenticated bounded Agent run consumes context and preserves source references. Freshness remains owner-declared rather than automatically verified; retrieval-quality evaluation and provider-backed prompt-injection acceptance remain incomplete.
4. **NEXUS developer agent — read-only foundation exists.** Python inventory/static analysis is bounded, emits file/line/rule evidence, and does not import or execute analyzed targets or modify files. Patch proposals are review-only. Coverage is intentionally narrow; broader language support, dependency analysis, and repository-scale performance validation remain open.
5. **Defensive cybersecurity lab — offline foundation exists.** Scoped, expiring authorization records and selected read-only configuration checks are implemented. This is not a comprehensive scanner or an active penetration-testing engine. Further checks must remain explicitly scoped, authorized, evidence-backed, and non-destructive.
6. **Packaging, backup/restore, release readiness — partial.** SQLite backup/restore verifies integrity and checksum, refuses destination overwrite, and has CI tests. SQLite backup does not include media assets, provider tokens, or encryption keys. A clean install/upgrade/rollback and restore drill on the intended target device, plus separately protected backup procedures for media and secret/key material, remain open.

### Release decision

**Do not label the entire project production-complete yet.** The signed-media code and relevant automated CI checks are merged, but live Instagram acceptance and target-device operational drills cannot be inferred from CI. The remaining work should proceed by closing each code-level regression with tests first, then recording external acceptance evidence without storing credentials or private media in the repository.


## Follow-up verification — 2026-11-02 UTC

The following hardening changes were merged after the release-readiness update above:

- **PR #79 — signed-media route integration test:** merged as `60e70badd453516b858e78c13624cb7897a63898`. CI passed on Python 3.11 and 3.12; the dispatcher test now requests the signed image through the actual ASGI route and checks content type, `nosniff`, `no-store`, and image signature bytes.
- **PR #80 — bounded NEXUS inventory:** merged as `0c253865807e7ab8125c4b6452ea0301b15a91fa`. CI passed after fixing the import-order lint finding. The analyzer now counts eligible Python candidates against the budget even when files are skipped for size, and reports `files_examined` separately from `files_scanned`.
- **PR #81 — offline cookie configuration checks:** merged as `d493728a7acfe223e3a9b3aa3b90b59b4232d811`. CI passed on Python 3.11 and 3.12 after correcting the test fixture's line separators. The defensive lab detects disabled Secure/HttpOnly cookie flags and does not echo configuration values.
- **PR #82 — distributable wheel asset verification:** merged as `f3fc765d54673bf551bb0cac2363f61275501b1c`. CI passed on Python 3.11 and 3.12; the pipeline builds a wheel and checks that `index.html`, `app.css`, and `app.js` are packaged.

These changes improve automated evidence for media delivery, bounded static analysis, defensive configuration review, and packaging. They do **not** close external deployment gates: public HTTPS reachability and edge controls still need deployment verification, live Instagram publishing needs a controlled authorized account test, and clean install/upgrade/restore drills still need to run on the intended target device. Do not store access tokens, signing keys, or private media in this repository.


## Packaging follow-up — 2026-11-02 UTC

- **PR #83 — status ledger synchronization:** merged. This section is now superseded by this follow-up where newer merged changes are listed.
- **PR #84 — clean wheel-install smoke test:** merged as `9c42cf9613231efe5caceb0bec41c700996bb213`. The CI pipeline creates a fresh virtual environment, installs the built wheel, imports the installed application, and requests `/health` under an isolated test database. Latest-head Backend CI and CI both passed; CI matrix coverage includes Python 3.11 and 3.12.
- This closes the *automated clean-wheel installation smoke test* gate. It does not establish a Windows target-device install/upgrade/rollback drill, restore drill, public HTTPS reachability, edge rate-limit/log-redaction configuration, or a live authorized Instagram publish/reconciliation test.

### Next acceptance gates

1. Run clean installation, upgrade, rollback, and SQLite restore on the intended Windows device; separately verify how media and secret/key material are backed up and restored.
2. Run an authorized Instagram Graph API acceptance test only after professional-account credentials are configured securely and the signed-media URL is reachable over public HTTPS.
3. Evaluate stale-source handling and prompt-injection behavior using a repeatable synthetic retrieval corpus before expanding Agent tool access.
4. Keep all production claims tied to exact-head CI plus relevant target-environment evidence.


## Packaging verification update — 2026-11-02 UTC

- **PR #84 — clean wheel-install smoke test:** merged as `9c42cf9613231efe5caceb0bec41c700996bb213`. Latest-head Backend CI and CI both completed successfully (workflow runs 41456196416 and 41456196431). The pipeline installs the built wheel into a fresh virtual environment and calls the packaged application's `/health` route with an isolated test database.
- This verifies a clean wheel install and basic application startup under CI. It does not replace installation, upgrade/rollback, or backup/restore drills on the intended Windows target device.
