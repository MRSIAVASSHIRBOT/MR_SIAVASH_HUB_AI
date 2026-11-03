# Defensive Python Static Analysis

The repository runs Bandit as a **blocking CI gate** for the application package on pull requests targeting `main`, pushes to `main`, manual dispatch, and a weekly schedule.

## Scope and enforcement

- Target: `backend/mrhub` only; tests and generated files are excluded.
- Minimum reported severity: medium (`--severity-level medium`).
- Minimum reported confidence: medium (`--confidence-level medium`).
- Enforcement: the workflow does **not** use `--exit-zero`; actionable findings at or above both thresholds fail the job.
- Execution: static AST-based checks; application modules are not imported or executed by the scanner.
- Permissions: GitHub Actions receives `contents: read` only.
- Reporting: findings and their locations appear in the workflow log.

A Bandit finding is a static-analysis signal, not automatically a confirmed vulnerability. Review the surrounding code and data flow before changing behavior. Suppressions must remain narrow, local to the relevant finding, and include a concise explanation of why the specific use is safe. Do not suppress a finding merely to make CI green; prefer a safer implementation and a regression test where practical.

## Relationship to existing checks

Bandit complements the project's read-only NEXUS Python analysis, defensive configuration review, Ruff, pytest, and `pip-audit`. It does not replace any of them and does not grant the agent permission to execute shell commands or modify a repository.

## Upstream component and licensing

The project uses the [Bandit](https://github.com/PyCQA/bandit) command-line package, published by PyCQA under Apache License 2.0. The package is installed only in the development/CI environment; it is not a runtime dependency. No Bandit source code is copied into this repository.
