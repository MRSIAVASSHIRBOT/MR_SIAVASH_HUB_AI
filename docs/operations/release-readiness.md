# Release Readiness Checklist

Use this checklist before tagging a release. A green unit-test suite is necessary but not sufficient.

Read the [release management policy](release-management.md) for the repository baseline, SemVer rules, dependency-lock requirements, release gates, update procedure, migration constraints, and rollback procedure.

## Clean installation
- [ ] Create a fresh Python 3.11 and/or 3.12 environment and install the approved dependency set from the checked-out commit.
- [ ] Confirm the installed package imports and the documented local startup command works.
- [ ] Build a wheel, inspect its package data, install it into a clean virtual environment, and run the health smoke test.
- [ ] Start with a new database and verify all schema migrations apply once and remain idempotent.
- [ ] Upgrade a copy of the prior release database and verify owner, task, workflow, approval, and content records remain readable.

## Local runtime and security
- [ ] Confirm the service binds to loopback by default.
- [ ] Complete owner setup and authenticated health/readiness checks.
- [ ] Verify worker pause/resume state survives a process restart and prevents new dispatch while paused.
- [ ] Confirm provider adapters remain disabled unless their required configuration is present.
- [ ] Check logs and API errors for credentials, tokens, private content, or raw provider payloads.

## Backup and recovery
- [ ] Create a database backup using the documented helper.
- [ ] Verify its manifest and perform a restore to a new path.
- [ ] Run the restore against a disposable database copy and confirm the application can initialize it.
- [ ] Back up media assets, encryption keys, and provider credentials separately using protected storage; do not bundle secrets into the database manifest.
- [ ] Record the tested backup timestamp, commit SHA, and restore result.
- [ ] For a migration rollback drill, restore the matching pre-upgrade backup to a new path and prove the previous application can start against it.

## CI and integration acceptance
- [ ] Confirm all required checks pass on the exact release commit.
- [ ] Run dependency auditing and review all findings.
- [ ] Exercise provider adapters with mocks and verify ambiguous external outcomes are quarantined rather than blindly retried.
- [ ] For any real external account, perform a controlled test only after explicit configuration and approval; verify provider-side results manually.
- [ ] Document known limitations and rollback steps before release.

## Platform acceptance
- [ ] Complete the Windows real-device checklist from [PR #101](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_HUB_AI/pull/101) on a real Windows machine; record the tested commit SHA and sanitized results.
- [ ] If macOS is a supported target, run and record a separate macOS acceptance pass. Otherwise state that macOS is not a supported/validated target.
- [ ] Do not infer Windows or macOS support from Linux CI.

Do not mark a release production-ready while any required gate above remains unverified.
