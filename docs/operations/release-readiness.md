# Release Readiness Checklist

Use this checklist before tagging a release. A green unit-test suite is necessary but not sufficient.

Read the [release management policy](release-management.md) for the repository baseline, SemVer rules, dependency-lock requirements, release gates, update procedure, migration constraints, and rollback procedure.

## Windows real-device acceptance
- [ ] Complete the [Windows Local Acceptance Checklist](windows-acceptance-checklist.md) on a real Windows machine and record the tested commit SHA and sanitized results.

## Clean installation
- [ ] Create fresh Python 3.11 and 3.12 environments and install the approved dependency set from the checked-out commit; record exact interpreter versions.
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
- [ ] Confirm all required checks pass on the exact release commit, including Python 3.11/3.12 CI, Backend CI, Defensive Python Scan, and applicable FFmpeg/FFprobe integration jobs.
- [ ] Run dependency auditing and review all findings.
- [ ] Exercise provider adapters with mocks and verify ambiguous external outcomes are quarantined rather than blindly retried.
- [x] Hosted Windows clean-wheel build/install smoke passed on the exact PR #326 head for Python 3.11 and 3.12; re-run and record the post-merge main result for each release candidate.
- [x] Checkout, setup-python, and upload-artifact references are pinned to verified immutable Node 24 action SHAs in the maintained CI workflows.
- [ ] For any real external account, perform a controlled test only after explicit configuration and approval; verify provider-side results manually.
- [ ] Document known limitations and rollback steps before release.

## Platform acceptance
- [ ] Complete [Windows Local Acceptance Checklist](windows-acceptance-checklist.md) on a real Windows machine; record the tested commit SHA and sanitized results. The checklist is a manual gate, not a claim of completion.
- [ ] Confirm the supported-platform statement explicitly. Current automated coverage includes Linux and Windows hosted FFmpeg integration; this is not equivalent to owner-device acceptance.
- [ ] If macOS is a supported target, run and record a separate macOS acceptance pass. Otherwise state that macOS is not a supported/validated target.
- [ ] Do not infer Windows or macOS device compatibility from Linux CI or hosted Windows jobs.

## Recent video snapshot integration
- [x] Review and merge [PR #276](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_HUB_AI/pull/276), which fences new snapshot-backed renders to the exact current draft revision for both snapshot-value and snapshot-ID submissions while preserving accepted idempotent retries.
- [x] Confirm the exact PR head passed Python 3.11/3.12, Backend CI, Defensive Python Scan and Linux/Windows FFmpeg integration.
- [x] Confirm the post-merge CI, Backend CI, Defensive Python Scan and Linux/Windows FFmpeg integration checks passed on exact main commit `6e0a41a52c5a9f28faaa9b5ffb15b971e1bbffd2` (runs `41845994226`, `41845994047`, `41845994201`, `41845993797`). Re-run this gate for any later release candidate.
- [ ] Complete the Windows real-device and representative-media workflow acceptance, including draft edits after accepted snapshot creation, replay of the accepted idempotency key, rejection of a new render from a stale snapshot, cancellation and output download.

Do not mark a release production-ready while any required gate above remains unverified. A hosted CI pass does not replace target-device acceptance, a coordinated restore drill, or owner approval.
