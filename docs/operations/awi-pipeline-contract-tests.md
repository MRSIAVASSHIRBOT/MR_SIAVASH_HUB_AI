# AWI cross-module contract tests

These tests exercise the proposal-only flow from plan revision through consistency validation, digest-bound review, integration preview, and deterministic summary export. They also verify that a candidate changed after review is rejected and that validation never grants execution permission.

The repository CI suite runs the backend tests and coverage, Ruff, Windows launcher checks, workflow security checks, and media-render integration checks. All required checks for the exact pull-request head must complete successfully before merge.
