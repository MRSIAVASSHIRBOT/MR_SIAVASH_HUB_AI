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
confidence, and remediation without echoing configuration values.

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
