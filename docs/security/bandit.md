# Defensive Python Static Analysis

The repository includes Bandit in its development toolchain and runs a bounded scan of the application package on pull requests, pushes to `main`, manual dispatch, and a weekly schedule.

## Scope

- Target: `backend/mrhub` only; tests and generated files are excluded from this scan.
- Minimum reported severity: medium.
- Minimum reported confidence: medium.
- Execution: static AST-based checks; application modules are not imported or executed by the scanner.
- Permissions: GitHub Actions receives `contents: read` only.
- Reporting: findings appear in the workflow log.

The initial workflow uses Bandit's report-only mode (`--exit-zero`). This intentionally establishes a baseline without unexpectedly blocking development on pre-existing findings. A finding is not automatically a confirmed vulnerability; validate its context and add a regression test when fixing it. Once the baseline has been reviewed, selected high-confidence rules can be promoted to a blocking gate.

## Relationship to existing checks

Bandit complements the project's read-only NEXUS Python analysis, defensive configuration review, Ruff, pytest, and `pip-audit`. It does not replace any of them and does not grant the agent permission to execute shell commands or modify a repository.

## Upstream component and licensing

The project uses the [Bandit](https://github.com/PyCQA/bandit) command-line package, published by PyCQA under Apache License 2.0. The package is installed only in the development/CI environment; it is not a runtime dependency. No Bandit source code is copied into this repository.
