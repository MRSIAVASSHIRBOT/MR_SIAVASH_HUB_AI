# MR_SIAVASH_ENGINEERING_HQ — Engineering Roadmap

**Baseline:** 2026-11-21 GitHub snapshot in [MASTER_STATUS.md](MASTER_STATUS.md)  
**Active development:** MR_SIAVASH_HUB_AI  
**Planning rule:** one primary development workstream; companion repositories receive only maintenance or dependency work unless the owner changes priority.

## Delivery principles

- Build complete vertical slices rather than adding disconnected modules.
- Prefer local-first, provider-neutral, modular-monolith architecture until measured requirements justify distribution.
- Keep each repository independently buildable and deployable.
- Treat CI success, runtime acceptance, and production deployment as separate evidence classes.
- Do not select paid providers, enable remote processing, or publish externally without explicit user action.
- Preserve current work; never clean branches or close PRs without evidence that they are obsolete.

## Milestones

### M0 — Establish portfolio control and reconcile the active queue (P0)

**Goal:** replace stale project snapshots with one verified, actionable engineering baseline.

Tasks:
- Reconcile [Issue #200](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_HUB_AI/issues/200) with current main, open PRs #472/#473, current branch inventory, and exact-head CI.
- Review PR #473's device authorization/lease-clock changes and wait for every exact-head check.
- Review PR #472's status evidence; verify its exact-head checks before merge consideration.
- Review EL_AI PR #78 independently; preserve its exact-head security evidence.
- Classify all remote branches as open-PR, dependency, active, historical, superseded, or unknown. Do not delete branches.
- Keep the five HQ reference documents synchronized with evidence.
- Record branch-protection gaps and the owner/admin-only remediation path.

**Exit criteria:**
- All open PRs have a documented state, changed-file scope, exact head SHA, check result, mergeability and dependency.
- Issue #200 no longer presents historical PRs as current work.
- No unresolved source-of-truth conflict remains in the current status record.
- All tasks have one owner role, a repository, a dependency and acceptance criteria.

### M1 — Stabilize HUB control plane and security (P0)

**Goal:** ensure the local platform's core state transitions, identity, policy and worker behavior are reliable.

Tasks:
- Audit authentication, owner scoping, policy evaluation, grants, approval binding and audit-event redaction.
- Verify Job/Workflow Engine idempotency, lease fencing, cancellation, recovery and unknown-outcome handling.
- Review Device Agent pairing, token rotation/reuse detection, task claim/outcome identity and transaction-clock semantics.
- Validate schema migration ordering and clean-install/upgrade paths.
- Validate Windows launcher and clean-wheel packaging.
- Establish repeatable local health/readiness and worker-heartbeat acceptance.

**Exit criteria:**
- Unit, integration, regression, security and packaging workflows pass on exact PR head.
- Owner isolation and fail-closed policy behavior have regression coverage.
- Expired/revoked credentials cannot authorize work after lock waits or stale leases.
- Clean Windows installation, API startup, worker startup, readiness and shutdown are reproducible.
- Backup/restore procedure is tested without modifying production data.

### M2 — Complete a media/content vertical slice (P1)

**Goal:** prove one user-owned content item can be prepared, rendered, inspected and retained safely.

Tasks:
- Reconcile Issue #182 with merged VideoGenerationProvider, durable jobs, consent, output limits and dashboard work.
- Verify deterministic FFmpeg rendering separately from generative provider behavior.
- Verify private source assets and generated outputs remain distinct.
- Validate output byte/duration/dimension limits, owner scope, cancellation, recovery and cleanup.
- Keep provider catalog read-only; require explicit provider selection and explicit start action.

**Exit criteria:**
- A bounded sample input produces a real MP4 through the deterministic renderer.
- Generated output is registered as a new private owner-scoped asset; original input is unchanged.
- No provider configured returns a clear unavailable result, not a fabricated output.
- Retry, timeout, cancellation, unknown outcome and cleanup tests pass.
- No remote paid provider is invoked implicitly.

### M3 — Controlled agent and device execution (P1)

**Goal:** demonstrate useful agent execution without unrestricted autonomy.

Tasks:
- Verify agent planning, context budgets, tool registry and policy revalidation.
- Verify owner-granted permissions, approval fingerprints, audit correlation and emergency stop.
- Integrate device operations only through named allow-listed capabilities.
- Validate task-plan dependency DAGs and success-gated advancement in EL_AI.
- Keep arbitrary shell execution, arbitrary executable paths and model-authored executable payloads out of the contract.

**Exit criteria:**
- Agent plans are inspectable before execution.
- Every consequential tool call is permission-checked at execution time.
- Revoked/expired grants fail closed.
- Dependent tasks advance only after all prerequisites succeed.
- Cancellation, retries, timeouts and unknown outcomes are auditable.
- No physical-device operation is claimed without an explicitly authorized test and observable result.

### M4 — Versioned cross-repository integration (P1)

**Goal:** ensure the three products work together without sharing internal databases or weakening privacy boundaries.

Tasks:
- Maintain a versioned Hub consumer contract and public status schema.
- Verify EL_AI Hub client origin/redirect policy, pairing scopes, refresh/revocation, request correlation and idempotency.
- Verify Website consumes only public projections and public Gateway context.
- Add compatibility tests for request/response schemas and error contracts.
- Define retry/backoff and timeout behavior for every remote call.
- Keep API version changes backward-compatible or explicitly coordinated.

**Exit criteria:**
- Contract tests pass in the provider and consumer repositories.
- No private memory, task result, token or owner context reaches public Website/Gateway requests.
- Correlation IDs and idempotency keys survive retries.
- Partial outages degrade only the affected integration.
- All three repositories remain independently testable and releasable.

### M5 — Staging and operational readiness (P1)

**Goal:** prove deployment and recovery without touching unrelated production resources.

Tasks:
- Resolve the dedicated Hub staging Worker design and isolated resource requirements in Issue #305.
- Reconcile Website Gateway source annotation with current source in Issue #120.
- Verify EL_AI runtime configuration using owner-managed secrets, without exposing token values.
- Establish backup/restore, observability, incident response and rollback evidence.
- Prepare a single-maintainer-safe branch-protection policy proposal for all three repositories.

**Exit criteria:**
- Staging resources are isolated and traceable to exact commits.
- Read-only and authenticated endpoint tests pass.
- Secrets are secret bindings and never appear in logs or API responses.
- Rollback is tested in staging.
- Runtime health is based on fresh observations, not source or CI inference.

### M6 — MVP release gate (P2)

**Goal:** release a reproducible, supportable product slice.

**Exit criteria:**
- Clean installation and upgrade are documented and verified.
- Critical workflows pass on exact release commit.
- No unresolved critical/high security blocker remains.
- User-facing capabilities match implemented behavior.
- Backup/restore and rollback are documented and exercised.
- Release notes, provenance and support runbook identify exact versions.
- Owner approves the specific production release.

## Dependency ordering

`M0 → M1 → M2/M3 → M4 → M5 → M6`

M2 and M3 may proceed in parallel only after M1's relevant security and persistence contracts are stable. M4 depends on versioned contracts from HUB and current consumer behavior in Website and EL_AI. M5 requires explicit resource and credential decisions. M6 cannot bypass any earlier acceptance gate.

## Immediate next work

1. Review and verify HUB PR #473 (security-sensitive implementation; checks were still running at snapshot).
2. Complete and verify HUB PR #472 (documentation-only status refresh; checks were still running at snapshot).
3. Review EL_AI PR #78 with independent QA and retain its exact-head pass evidence.
4. Reconcile HUB Issue #200 against the live queue and this baseline.
5. Establish a safe branch-inventory classification; preserve all branch refs.
6. Defer new feature work until M0 is complete.
