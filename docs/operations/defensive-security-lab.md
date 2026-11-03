# Defensive Security Lab — Offline Review Contract

## Authorization boundary

Every review request must provide a `DefensiveReviewScope` containing:
- a nonblank authorization reference;
- one or more unique, bounded asset identifiers;
- an expiry timestamp with timezone;
- the fixed `offline_static_only` mode.

The selected `asset` must exactly match one of the declared identifiers. Expired
scopes and scopes longer than 30 days are rejected. This request-level
authorization declaration is evidence supplied by the owner; it is not an
independent verification of third-party ownership.

## Configuration review

`POST /security-lab/config-review` reviews caller-supplied configuration text
for selected risky patterns. It returns file/line evidence, severity,
confidence, and remediation without echoing configuration values. Confidence
describes confidence in the pattern match, not exploitability or impact.

## Dependency manifest review

`POST /security-lab/dependency-review` performs a bounded offline review of a
requirements-style manifest. It identifies:
- dependencies without an exact version pin;
- direct URL, VCS, and editable dependencies;
- nested requirement/constraint includes that were not expanded;
- custom package-source directives requiring manual trust review;
- unsupported requirement syntax that needs manual review.

It does not contact package indexes, install packages, resolve dependencies,
consult a vulnerability database, or claim that a package is free of known
CVEs. A future vulnerability audit must use an explicitly approved advisory
snapshot or a separately authorized network workflow.

## Hard limits

- Maximum input size: 1 MB per request.
- Authorization lifetime: at most 30 days.
- Only the exact declared asset can be reviewed.
- No active scans, network requests, shell execution, package installation,
  filesystem modification, or credential collection.
- Audit events record only safe outcome metadata; raw configuration,
  dependency manifest contents, authorization references, and values are not
  written to audit logs.


## Structured security log review

`POST /security-lab/log-review` accepts normalized JSON Lines (JSONL) records under the same exact-asset authorization scope. It is an offline triage aid, not a SIEM, attribution tool, incident verdict, or active scanner.

Supported event types are `auth.login.failed`, `auth.login.succeeded`, `authorization.role_changed`, `audit.integrity_failed`, and `audit.record_deleted`. Repeated authentication failures are correlated using an internal SHA-256 pseudonym of the supplied actor identifier; raw actor identifiers and log values are never returned or written to audit metadata. Findings contain only rule IDs, severity/confidence, filename, line number, a generic explanation, and remediation guidance.

The input is limited to 1 MB and 10,000 lines. Malformed or unsupported records—including parser failures caused by oversized numeric tokens or excessive nesting—are counted but not echoed. No network requests, package operations, target modifications, or active tests are performed. Results are heuristic triage signals and require review against the original authorized source.
