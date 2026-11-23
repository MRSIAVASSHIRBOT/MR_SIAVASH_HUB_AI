# H10 Release Readiness Gates

Status: checklist proposal; not a release certification.
Scope: release acceptance for MR_SIAVASH_HUB_AI. This checklist supplements CI and does not replace security review.

## 1. Candidate identity and source control
- [ ] Candidate commit SHA is recorded; the working tree is clean.
- [ ] All intended PRs are merged; no release-critical open PR or known unresolved conflict remains.
- [ ] Release notes list user-visible changes, limitations, and migration notes.
- [ ] Version/tag is selected deliberately; do not tag a release before the remaining gates pass.

## 2. Automated CI evidence
For the exact candidate SHA, review and record:
- [ ] Python 3.11 CI pass.
- [ ] Python 3.12 CI pass.
- [ ] Backend CI pass (including Ruff, pip-audit, and coverage execution).
- [ ] Windows wheel smoke pass for Python 3.11 and 3.12.
- [ ] Windows launcher validation pass, if triggered for the candidate.
- [ ] Video Render Integration pass for Linux and Windows, if triggered for the candidate.
- [ ] Defensive Python Scan and Workflow Security Audit pass, if triggered for the candidate.
- [ ] No required job is pending, skipped unexpectedly, cancelled, or run against a different SHA.
- [ ] Coverage report reviewed for changed critical modules; total percentage alone is not a substitute for assertions around security/recovery paths.

## 3. Test evidence and regressions
- [ ] Unit and integration suites pass on the exact candidate.
- [ ] Workflow ordering, stable step identity, resume, duplicate-execution protection, and blocked dependencies verified.
- [ ] Retry ceilings/backoff, stale lease recovery, cancellation, and ambiguous external outcomes verified.
- [ ] Planning remains separate from authorization and tool execution.
- [ ] Tool schema/registry validation, permission enforcement, and untrusted tool-output handling verified.
- [ ] Memory owner scoping, expiry, privacy filtering, and retrieval behavior verified.
- [ ] API auth, error responses, readiness, liveness, worker heartbeat, and rate-limit configuration reviewed.
- [ ] Migration tests cover a clean database and representative existing database upgrades.
- [ ] UI, packaged assets, and API smoke checks pass from a clean wheel installation.

## 4. Dependency and security review
- [ ] Dependency audit has no unresolved release-blocking vulnerability.
- [ ] Secret scanning and static security scan reviewed; no credentials or sensitive test artifacts in the release.
- [ ] Permissions and environment configuration use least privilege.
- [ ] External providers/tools are disabled or configured intentionally; ambiguous provider operations have safe reconciliation behavior.
- [ ] Resource limits, timeouts, retry budgets, and worker concurrency are reviewed.

## 5. Database and backup/restore
- [ ] Migration chain and schema version are recorded.
- [ ] Backup created before upgrade.
- [ ] Backup restore procedure has been exercised in a non-production/test environment.
- [ ] Rollback limitations for irreversible data migrations are understood and documented.

## 6. Deployment acceptance
- [ ] Configuration/environment variables reviewed; no secrets in logs.
- [ ] Health and readiness checks pass after deployment.
- [ ] Worker heartbeat and queue processing verified.
- [ ] Basic API and UI smoke tests pass.
- [ ] Logs/metrics are checked for unexpected errors, retry storms, or queue stalls.

## 7. Rollback and post-release
- [ ] Rollback target and steps are documented.
- [ ] Rollback decision criteria and responsible operator are identified.
- [ ] Post-release observation window and key signals are defined.
- [ ] Release record includes candidate SHA, CI run links, migration version, backup identifier, operator, and outcome.

## Stop conditions
Do not declare a stable release if any required CI check is failing or unresolved, candidate SHA evidence is mismatched, a migration/restore gate is incomplete, security-critical findings remain, or health/readiness/worker acceptance fails. Record the blocker and keep the candidate unreleased.

## Release evidence record (copy for each candidate)
- Candidate SHA:
- Version/tag:
- CI links and conclusions:
- Coverage report reviewed:
- Migration/schema version:
- Backup/restore evidence:
- Security/dependency findings:
- Deployment health/readiness:
- Rollback target:
- Operator/date:
- Final decision (release / hold):
