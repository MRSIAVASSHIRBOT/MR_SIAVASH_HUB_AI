# MR_SIAVASH_ENGINEERING_HQ — Task Registry

**Baseline:** 2026-11-21  
**Registry owner:** Engineering Coordinator  
**Rule:** each task has one accountable role, one primary repository, explicit dependencies and verifiable acceptance criteria. Existing GitHub Issues/PRs remain the implementation records; this registry coordinates rather than duplicates them.

## Active tasks

| Task ID | Priority | Primary repo | Accountable role | Source | State |
| --- | --- | --- | --- | --- | --- |
| HQ-001 | P0 | HUB | QA + Backend | PR #473 | IN PROGRESS — exact-head checks running |
| HQ-002 | P0 | HUB | Project Management + QA | PR #472 | IN PROGRESS — exact-head checks running |
| HQ-003 | P0 | HUB | Architecture + Project Management | Issue #200 | BLOCKED — historical queue snapshot requires reconciliation |
| HQ-004 | P0 | HUB | DevOps + Security | Issue #304 | BLOCKED — branch protection admin not available in connector |
| HQ-005 | P1 | EL_AI | Integration + QA | PR #78 | READY FOR REVIEW — exact-head CI and security audit passed |
| HQ-006 | P1 | HUB | Integration + Cloud Operations | Issue #305 | BLOCKED — dedicated isolated staging resource/approval |
| HQ-007 | P1 | HUB | Backend + QA | Issue #182 | IN PROGRESS — merged foundation; provider/runtime acceptance remains |
| HQ-008 | P1 | Website | DevOps + QA | Issue #120 | BLOCKED — fresh Cloudflare source/version readback required |
| HQ-009 | P1 | Website | DevOps + Security | Issue #70 | BLOCKED — branch protection admin not available in connector |
| HQ-010 | P1 | EL_AI | DevOps + Security | Issue #5 | BLOCKED — branch protection admin not available in connector |
| HQ-011 | P1 | EL_AI | Integration + QA | Roadmap Milestone 2/3 | BLOCKED — owner-managed Telegram runtime secret and live test setup |
| HQ-012 | P1 | All three | Architecture + QA | This HQ baseline | IN PROGRESS — contract compatibility and branch inventory mapping |
| HQ-013 | P2 | HQ | Project Management | Existing SPC Control Center | BLOCKED — Notion write tools not available to this connection |

## Acceptance details

### HQ-001 — HUB device authorization and task-lease timing

- Review PR #473 diff and affected transaction boundaries.
- Confirm expiry and authorization clocks are read only after the SQLite writer lock is acquired.
- Confirm stale leases cannot authorize late outcomes or block queue recovery.
- Verify pairing, refresh, revocation, claim, outcome, reconciliation and cancellation regression coverage.
- **Accept only when:** all required checks pass on the current PR head, no unresolved security review finding remains, and the final diff is reviewed.

### HQ-002 — HUB current status documentation

- Review PR #472 changed paths and its current main/companion evidence.
- Verify every SHA and workflow link against current repository heads.
- Preserve historical snapshots and label them as historical.
- **Accept only when:** documentation matches current evidence and every required check passes on the exact PR head.

### HQ-003 — Reconcile recovery Issue #200

- Replace obsolete references to historical PR #196/#198/#183 as active queue state with current open PRs #472/#473 and current main SHA.
- Record the complete 472-branch inventory and a non-destructive classification plan.
- Reconcile migration, dependency and release evidence from current source.
- **Accept only when:** every open PR has a state, exact head, checks, changed files and dependency; no branch is deleted or PR closed merely for cleanup.

### HQ-004 / HQ-009 / HQ-010 — Branch protection

- Prepare a consistent single-maintainer-safe proposal requiring PRs and exact-head CI while preventing force-push and branch deletion.
- Identify exact required check names from current workflows.
- **Accept only when:** repository admin applies the policy and a fresh GitHub read confirms enforcement with a test PR.
- Current connector limitation: branch-protection/ruleset mutation is not exposed; the read endpoint returned 403. Do not claim remediation.

### HQ-005 — EL_AI Hub redirect protection

- Independently review PR #78 and confirm the authorization header is never forwarded to a redirect target.
- Confirm Python 3.11/3.12 CI and Workflow Security Audit pass on exact head `d093069a073f6e46274b38ea8f3f34622b20830c`.
- **Accept only when:** QA review is complete and the owner-approved merge path is used. Do not merge solely to clear the queue.

### HQ-006 — Isolated Hub staging

- Keep Website preview and any unrelated production Worker resources separate.
- Specify dedicated Hub staging Worker, dedicated hostname, least-privilege identity, secrets, bindings, smoke tests and rollback.
- **Accept only when:** owner approves the exact resource/scope/cost and isolated staging tests pass. No production route or Gshop resource changes.

### HQ-007 — Video generation lifecycle

- Reconcile Issue #182 with already merged provider-neutral protocol, durable owner-scoped jobs, consent gates, cancellation and private asset lifecycle.
- Verify deterministic renderer separately from generative provider.
- **Accept only when:** real bounded MP4 rendering and lifecycle tests pass; no provider means an explicit unavailable result.

### HQ-008 — Website Gateway source reconciliation

- Re-read Cloudflare Worker deployment metadata and compare its source annotation with current Website main.
- Review migrations, preview acceptance, backup and rollback before any release proposal.
- **Accept only when:** source/version parity is evidenced and any production release is separately approved.

### HQ-011 — EL_AI live runtime acceptance

- Keep Telegram token and owner IDs in owner-managed secret storage only.
- Run local read-only preflight first.
- Test pairing, opt-in, scopes, revocation, polling/update cursor and public/private isolation using a test bot.
- **Accept only when:** explicit live test evidence is recorded. No token is requested in this document or committed to Git.

### HQ-012 — Cross-repository contract compatibility

- Compare Hub consumer references, Website public status schema and EL_AI client contracts.
- Validate versioning, correlation, idempotency, retry, timeout and privacy behavior.
- **Accept only when:** provider and consumer contract tests pass on exact source SHAs.

### HQ-013 — Notion dashboard mirror

- Existing Notion SPC Control Center is the canonical management entry point.
- Current Notion connection provides search/fetch but does not expose page creation/update as available.
- **Accept only when:** write access becomes available and the existing SPC Control Center can be updated without creating a duplicate dashboard.

## Initial specialist-chat assignments

| Specialist conversation | Initial assignment | Deliverable |
| --- | --- | --- |
| HQ Control Center | Own task priority, conflicts, dependencies and status | Updated task registry and weekly evidence snapshot |
| System Architecture | Review HQ ownership, ADR-0006 compatibility and API boundaries | Contract/ADR findings; no duplicate dashboard |
| HUB Backend | Review PR #473 and Issue #200 recovery requirements | Transaction/security review and focused fixes if needed |
| AI & Agent Engineering | Map current Agent/Memory/Tool capabilities to M1/M3 acceptance | Capability matrix and gaps; no new provider activation |
| Frontend & Product | Audit HUB operator UI and Website integration surface | UX/functional gaps only; avoid unrelated redesign |
| Integration Engineering | Review Hub/Website/EL_AI API contracts and client behavior | Compatibility matrix and contract-test plan |
| QA & Security | Independently validate PR #473, #472 and #78 exact heads | Findings with severity, evidence and safe remediation |
| DevOps & Release | Verify workflows, branch governance limitations, staging and release boundaries | CI/release evidence matrix and admin-only blockers |
| Project Learning Lab | Teach one real decision from each accepted task | Beginner-friendly explanation, glossary and exercises |

## Duplicate-work prevention

- Use the HQ task ID in branch names, PR descriptions or commit references when practical.
- Do not create a second Issue if an existing Issue already owns the work.
- A task can have supporting contributors, but only one accountable role.
- Record changed paths and branch/head SHA before parallel implementation.
- QA remains independent from the implementation owner.
- Mark DONE only after acceptance evidence is attached.
- Update this registry when the task state changes; do not infer completion from code generation or PR creation.


## Exact-head CI status correction — 2026-11-21 19:05 UTC

- **HQ-001 / PR #473:** BLOCKED pending investigation of Windows failure `test_model_device_task_creation_uses_time_after_write_lock_for_grants` (69 passed, 1 failed). CI was cancelled and Backend CI was still running at last read. Do not merge until the failure is understood and every required check passes on the updated exact head.
- **HQ-002 / PR #472:** IN PROGRESS. Workflow Security Audit, Defensive Python Scan and Video Render Integration passed; CI was cancelled and Backend CI remained in progress. Cancelled is not PASS.
- **HQ initialization / PR #474:** documentation-only PR containing these five reference files. Workflow Security Audit, Defensive Python Scan and Video Render Integration passed; CI and Backend CI were still running at last read.


## Branch inventory count correction — 2026-11-21 UTC

The complete paginated Hub branch inventory contains 472 remote branches (pages 1–4: 100 each; page 5: 72). The prior 372 figure was an arithmetic error. No branch was deleted or modified.


# Four-project task registry correction — 2026-11-21

This section supersedes the earlier three-project registry scope. The portfolio now tracks all four repositories. Existing PRs/issues remain the work records; no duplicate implementation issues are created.

## Refreshed active queue

| Task ID | Priority | Repository | Accountable role | Existing source | Current state |
| --- | --- | --- | --- | --- | --- |
| HQ-001 | P0 | HUB | Backend + QA + Security | PR #473 | DONE — merged as `9ae07b0`; failed Windows regression rerun and merged-main Windows validation passed |
| HQ-002 | P0 | HUB | Project Management + QA | PR #472 | READY FOR REVIEW — all five exact-head checks passed |
| HQ-003 | P0 | HUB | Architecture + Project Management | Issue #200 | IN PROGRESS — refresh issue against current four-repo portfolio and current merged PRs |
| HQ-004 | P0 | All four | DevOps + Security | HUB #304, Website #70, EL_AI #5; EL_AGENT branch metadata | BLOCKED — all four main branches report unprotected; GitHub branch protection administration unavailable |
| HQ-005 | P1 | EL_AI | Integration + QA + Security | PR #78 | DONE — merged into main as `39ea955`; exact-main CI/security/Scorecard passed |
| HQ-006 | P1 | HUB | Integration + Cloud Operations | Issue #305 | BLOCKED — isolated staging resource and owner approval required |
| HQ-007 | P1 | HUB | Backend + QA | Issue #182 | IN PROGRESS — provider-neutral durable foundation merged; render/provider/runtime acceptance remains |
| HQ-008 | P1 | Website | DevOps + QA | Issue #120 | BLOCKED — fresh Cloudflare source/version readback required |
| HQ-009 | P1 | Website | DevOps + Security | Issue #70 | BLOCKED — branch protection admin unavailable |
| HQ-010 | P1 | EL_AI | DevOps + Security | Issue #5 | BLOCKED — branch protection admin unavailable |
| HQ-011 | P1 | EL_AI | Integration + QA | Runtime acceptance | BLOCKED — owner-managed Telegram runtime secret and live test setup |
| HQ-012 | P1 | All four | Architecture + Integration + QA | HQ four-project baseline | IN PROGRESS — contract compatibility, ownership and release matrix |
| HQ-013 | P2 | HQ | Project Management | Existing SPC Control Center | BLOCKED — Notion write actions unavailable |
| HQ-014 | P1 | EL_AGENT | QA + Desktop Platform | EL_AGENT README/ROADMAP | IN PROGRESS — clean Windows 11 install, loopback API, scheduler/recovery and real-device acceptance; no new feature branch |
| HQ-015 | P1 | EL_AGENT | Integration + QA + Security | PR #23 | DRAFT / CI PASS — Windows Hub task consumer; physical Windows 11 and isolated Hub Staging acceptance pending |
| HQ-016 | P1 | EL_AGENT | Android + QA + Security | PR #25 | DRAFT / CI PASS — Android planner/offline runtime/Hub consumer; physical Android and isolated Hub Staging/revocation acceptance pending |
| HQ-017 | P1 | HUB + EL_AGENT | Architecture + Backend + Integration | HUB device-task contract and EL_AGENT PRs #23/#25 | IN PROGRESS — verify contract compatibility and ensure only one task owns each contract change |

## EL_AGENT task acceptance criteria

### HQ-014 — Standalone Windows and Android acceptance
- Windows: clean Windows 11 install/uninstall; local API bound only to loopback; bearer auth; fixed app aliases; explicit screenshot locality; scheduler/cancel/recovery; no admin elevation; startup install/removal; local Ollama-only mode.
- Voice: microphone is user-initiated, bounded, visibly active and local-only by default; unsupported speech is rejected.
- Android: physical install; Keystore credential persistence; owner pairing; Unpair/re-pair; foreground microphone permission; file picker URI grant bounds; offline model import limits; no background UI automation.
- **Accept only when:** platform test reports include OS/device version, exact app commit/build, reproducible steps and observed result. CI is not physical-device acceptance.

### HQ-015 — Windows Hub task consumer PR #23
- Review all 14 changed files and task claim/execute/report lifecycle.
- Verify exact device binding, allowlisted actions, owner confirmation, scope/lease/deadline checks, OS credential vault and no plaintext migration unless vault write is verified.
- Test cancellation, grant revocation/expiry, stale lease, timeout and ambiguous outcome; do not replay uncertain operations.
- **Accept only when:** isolated Hub Staging round-trip and physical Windows 11 tests pass, in addition to exact-head CI/security review. Keep Draft until then.

### HQ-016 — Android Hub task consumer and planner PR #25
- Review the 42-file consolidated diff, planner schema, bounded step/dependency handling, deterministic Android capability policy, document picker, provider routing and offline model import.
- Verify no paid provider fallback, no model-authored executable payload, no silent phone call, no background microphone/UI automation, and no action after Unpair wins the credential/action fence.
- **Accept only when:** exact-head Python/Android CI remains green, physical-device tests pass, isolated Hub Staging pairing/task/revocation round-trip passes, and security review is clear. Keep Draft until then.

### HQ-017 — Hub/device contract compatibility
- Hub owns issuance, policy/grants, lease, revocation and reconciliation; EL_AGENT owns platform execution and local OS checks.
- Validate versioning, exact device identity, scopes, action allowlist, idempotency, correlation, deadline, cancellation and unknown outcomes.
- **Accept only when:** contract tests run against synthetic test identities on both Windows and Android clients and Hub provider code; no production device operation is used.

## Eight specialist workstreams — EL_AGENT coverage

1. **System Architecture:** own four-project boundaries and standalone EL_AGENT architecture; prevent EL_AGENT/EL_AI conflation; document platform-specific capability contracts.
2. **Backend Engineering:** review Hub device-task APIs and EL_AGENT Windows runtime/credential/task persistence; keep authorization at execution boundary.
3. **AI & Agent Engineering:** review Android planner, local/cloud provider routing, model imports, bounded plans and the distinction between model proposal and deterministic policy authorization.
4. **Integration Engineering:** own Hub↔EL_AGENT pairing/task contract; separately verify EL_AI→Hub and Website public projection; no direct DB sharing.
5. **QA Engineering:** own Windows 11 and physical Android acceptance matrix, task lifecycle/recovery, platform regression and CI exact-head evidence.
6. **Security Engineering:** own Windows credential vault, Android Keystore, local loopback/token boundary, app/document/microphone permissions, redirect refusal, revocation and threat review.
7. **DevOps & Release Engineering:** own Python/Windows packaging, Android APK build/artifacts, dependency/supply-chain checks, staging, provenance, rollback and branch governance proposal.
8. **GitHub & System Audit:** own all-four-repository branch/commit/PR/issue/CI inventory, exact SHA evidence, stale branch classification and duplicate-work detection.

The Chief Engineering Coordinator remains accountable for portfolio priorities, conflict resolution, task assignment and the single status record; this is coordination, not a ninth implementation workstream.

## Duplicate-work prevention update
- PR #23 is the owner of Windows Hub task-consumer implementation; do not create a second Windows consumer task.
- PR #25 is the owner of the consolidated Android planner/offline-runtime/Hub-consumer implementation; do not revive its closed stacked PRs as separate active tasks.
- HUB device-task API and policy remain owned by HUB. EL_AGENT consumes the contract and owns platform-side enforcement.
- Local Windows/Android platform acceptance is a QA task, not a duplicate feature implementation.
- Do not create new EL_AGENT issues while the existing PRs and HQ task IDs already own the work.
