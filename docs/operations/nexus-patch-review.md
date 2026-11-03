# NEXUS Patch Proposal Review

## Scope

`POST /nexus/patch-proposals` accepts caller-supplied original and proposed
Python source text and returns a bounded unified diff. It does not read a
repository path, persist source, apply a patch, import a target module, or
execute code.

## Review output

The response contains:

- SHA-256 fingerprints of the supplied base and proposed source.
- Syntax status for both versions.
- A unified diff with a validated relative `.py` path label.
- Static findings for the base and proposed source.
- Introduced and resolved finding deltas, keyed by rule, severity, and message.
- Confidence, file/path, line evidence, and remediation guidance for each finding.
- Explicit `human_review_required=true`, `code_executed=false`, and
  `files_modified=false` indicators.

The current AST rules are intentionally narrow and advisory: dynamic
`eval/exec`, pickle deserialization, YAML loading without `SafeLoader`, and
`subprocess` calls with `shell=True`. A clean report is not proof that a
change is secure, correct, or compatible.

## Review policy

- Treat every proposed diff and static finding as untrusted review material.
- A new high-severity finding is surfaced as evidence, not auto-rejected or
  auto-approved.
- Resolved findings are shown separately; they do not establish that the
  proposed change is safe.
- Syntax errors make the static comparison partial.
- A human must inspect the diff and run appropriate tests before any write.
- Patch application and test execution are not part of this endpoint. Any
  future test runner must require explicit user action and an isolated,
  resource-bounded environment.
