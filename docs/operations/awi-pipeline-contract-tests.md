# AWI cross-module contract tests

These tests exercise the proposal-only flow from plan revision through consistency checks, digest-bound review, integration preview, and summary export. They also test digest tampering rejection and the invariant that validation never grants execution permission.

The repository's existing CI workflow runs pytest, coverage, Ruff, frontend syntax and gateway tests, plus package smoke tests. Opening this PR should trigger the repository CI on the PR head; CI results must be inspected before merge.
