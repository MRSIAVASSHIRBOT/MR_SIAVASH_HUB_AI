# Continuous Execution and Engineering Governance Standard

This document defines the operating standard for maintainers, contributors, and delegated project work. It is intended to keep delivery continuous without weakening correctness, security, or owner control.

## 1. Execution loop

For every bounded work item:

1. Inspect the current repository state, relevant code, open pull requests, and existing tests before editing.
2. State the intended outcome and identify dependencies and risk.
3. Make the smallest coherent change on a dedicated branch. Do not edit `main` directly.
4. Run the narrowest relevant tests first, then the broader required checks.
5. Inspect the resulting diff, test output, repository status, and generated artifacts.
6. Fix regressions and repeat the relevant checks.
7. Commit with a specific message and open or update a pull request with evidence.
8. Continue with independent work while unrelated CI jobs run; do not wait idly when safe parallel work exists.
9. Stop only when the work is complete, a real external dependency blocks progress, an owner decision is required, or further action would create material risk.

A task is not complete merely because code was written or a pull request was opened.

## 2. Evidence and status vocabulary

Every report must distinguish:

- **DONE** — change is committed and its acceptance criteria are met.
- **IN PROGRESS** — work is actively being performed; identify the current step.
- **BLOCKED** — a specific external dependency or missing permission prevents progress.
- **NOT RUN** — a check was not executed; state why.
- **PASS** — a named check completed successfully on the exact commit SHA stated.
- **FAIL** — a named check completed and failed; include the actionable failure.

Never report a check as passing based on an earlier commit, a different branch, a partial workflow, or an inferred result. A cancelled or skipped check is not a pass.

## 3. Pull request requirements

Every non-trivial pull request should include:

- Problem statement and user-visible or operational impact.
- Scope and explicit non-goals.
- Changed paths and a concise explanation of important design choices.
- Security, privacy, migration, compatibility, and rollback considerations where relevant.
- Exact commit SHA used for validation.
- Commands and outcomes for tests, lint, dependency audit, packaging, and platform checks.
- Known limitations and checks that remain NOT RUN or BLOCKED.

Keep pull requests focused. Avoid combining unrelated feature work, maintenance fixes, and release administration in one change.

## 4. Integration and dependency management

- Keep `main` as the integration baseline; use feature branches for work.
- Declare pull-request dependencies explicitly in the PR description and management notes.
- Do not merge a dependent UI or integration PR before its base capability is accepted.
- Before merging overlapping changes, compare changed paths and inspect the combined behavior, not only each PR in isolation.
- Rebase or update dependent branches only after their parent change has a stable, reviewed target.
- Prefer small, reversible integration steps. Do not use force-push to overwrite shared work.
- Do not close, delete, or merge another contributor's work merely to reduce queue size.

## 5. Required quality gates

Select checks according to the changed surface. At minimum, relevant Python changes should pass:

- Ruff lint and formatting/import checks.
- Targeted unit and integration tests.
- The repository's required backend and full CI workflows.
- Dependency audit and defensive static analysis.
- Wheel/package-data validation when packaging, entry points, or static assets change.

For API, authentication, jobs, agents, tools, or integrations, add or run tests for authorization boundaries, owner scoping, idempotency, bounded input/output, failure handling, and safe defaults as applicable.

For database or persistence changes, verify migration ordering, idempotency, upgrade behavior, backup boundaries, and recovery implications.

A green CI badge is evidence for the checks it actually ran; it is not proof of real-device acceptance, external provider behavior, or production readiness.

## 6. Security and owner-controlled actions

Routine, low-risk, reversible development and documentation work may proceed without repeated owner confirmation.

Keep explicit owner control for:

- Publishing a public release or creating a release tag.
- Deleting data, branches, repositories, backups, or user content.
- Exposing secrets, private data, or credentials.
- Enabling external integrations that can execute actions or incur costs.
- Changing production access, billing, or irreversible infrastructure.
- Merging changes when required security, compatibility, or acceptance evidence is missing.

Never commit real credentials, tokens, private keys, personal data, or production datasets. Use placeholders and document required environment variables.

## 7. Parallel work and role boundaries

Delegated contributors should work independently within clearly assigned ownership:

- Feature development owns new product capabilities.
- Maintenance owns defects, reliability, security hardening, and regression fixes.
- Integration review owns third-party/tool assessment, contracts, configuration consistency, and integration acceptance.
- Independent QA owns verification and defect reports; QA does not silently implement the fix it is meant to validate.
- Release management owns versioning, packaging, installation, upgrade, rollback, and release evidence.
- Project management owns priorities, dependency ordering, scope conflicts, and evidence-based status; it does not claim specialist work it has not performed.

When work overlaps, communicate the exact file paths, branch, commit SHA, and dependency. Do not have multiple contributors modify the same files concurrently without an explicit coordination plan.

## 8. Final report format

Each completed work batch reports:

1. Outcome and user/project impact.
2. Branch, commit SHA, and pull request URL.
3. Files changed and why.
4. Tests/checks with exact PASS, FAIL, BLOCKED, or NOT RUN states.
5. Risks, limitations, and follow-up dependencies.
6. The next independent action, if any.

Reports must be concise, factual, and reproducible. Do not claim background execution after the active work session ends.
