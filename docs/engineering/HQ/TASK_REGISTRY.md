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
