# Release management and readiness

This document defines the repeatable release process for MR_SIAVASH_HUB_AI.
It is an operational checklist, not a claim that a release is currently ready.

## Current repository baseline (2026-11-03)

| Area | Observed state | Release implication |
|---|---|---|
| Package version | `0.1.0` in `pyproject.toml` | Treat as the current development metadata version; do not infer that a public release exists. |
| Python floor | `>=3.11` | Python 3.11 is the declared minimum. |
| CI Python matrix | 3.11 and 3.12 in `.github/workflows/ci.yml` | These are the currently configured CI targets, not proof of successful execution on every OS. |
| Backend CI | Python 3.11; dependency audit, Ruff, pytest | Keep this workflow aligned with the main CI policy. |
| Build | CI builds a wheel and checks that UI assets are packaged | Useful packaging gate; requires a completed runner job to count as evidence. |
| Wheel smoke test | CI installs the wheel into a clean virtual environment and calls `/health` using TestClient | This is an automated Linux/Python smoke test, not a Windows-device acceptance test. |
| Dependency declarations | Runtime and development dependencies are declared in `pyproject.toml` using version ranges | Fresh installs can resolve different transitive dependency versions over time. |
| Lock file | No `uv.lock`, `poetry.lock`, `requirements.txt`, or `requirements-dev.txt` was found at the repository root during this review | Reproducible, fully pinned deployment dependency resolution remains an open release-hardening item. |
| Changelog | No root `CHANGELOG.md` existed at review time | This file establishes the project changelog. |
| Backup | Local SQLite backup/restore helpers and an operations guide exist | Database backup alone does not include keys, provider credentials, or media assets. |
| CI availability | Issue #66 records jobs failing before runner assignment, with no steps or runner logs | A red pre-runner job is infrastructure-blocked, not a test failure; neither red nor green status should be misrepresented. |
| Windows acceptance | PR #101 proposes a real-device checklist | Windows acceptance remains unverified until a recorded run is completed on the target device. |

## Semantic Versioning policy

Use `MAJOR.MINOR.PATCH`:

- **MAJOR**: an incompatible public API, configuration, data, or operational contract change.
- **MINOR**: backward-compatible functionality or a new supported capability.
- **PATCH**: backward-compatible bug fixes, security fixes, and packaging/documentation corrections.

Until the project declares a stable 1.0 API, use `0.y.z` with care: minor increments may contain breaking changes under SemVer's pre-1.0 rules. Document any such incompatibility explicitly.

The version in `pyproject.toml`, the release tag (`vX.Y.Z`), and the GitHub Release title must match. Do not create or publish a tag from an unreviewed or unvalidated commit. Do not overwrite an existing release tag.

## Dependency and build policy

1. Keep direct runtime and development dependencies declared in `pyproject.toml`.
2. Review dependency changes for supported Python versions, license, maintenance status, known vulnerabilities, and transitive impact.
3. Run `pip-audit --skip-editable` against the resolved environment and record the result.
4. The current version ranges are not a complete dependency lock. Before promising byte-for-byte reproducible installs or publishing a deployment bundle, adopt and maintain one canonical lock strategy (for example, a committed `uv.lock` with a documented uv workflow). Do not maintain multiple competing lock sources.
5. Build and inspect a wheel; verify all runtime package data, including `mrhub/web/index.html`, `mrhub/web/app.css`, and `mrhub/web/app.js`.
6. Install the built wheel into a fresh environment outside the source tree and perform an import and health smoke test.

## Release gates

A release candidate must satisfy all applicable gates:

- [ ] The release commit is on the intended branch and has been reviewed.
- [ ] Version metadata, tag name, changelog, and release notes agree.
- [ ] Full CI completes on the exact candidate commit, with actual runner assignment, steps, and logs.
- [ ] Python 3.11 and 3.12 test matrix passes.
- [ ] Dependency audit and lint pass with no unresolved release-blocking findings.
- [ ] Wheel builds successfully and required UI assets are present.
- [ ] Clean wheel installation and application health smoke test pass.
- [ ] Database schema/migration behavior is reviewed; upgrade and downgrade/rollback limitations are documented.
- [ ] Backup and restore are tested against a disposable copy; encryption keys and media assets are handled separately.
- [ ] Windows real-device acceptance is recorded when Windows is a supported target. Linux CI is not a substitute.
- [ ] External integrations remain disabled unless their own credentials, network reachability, and controlled acceptance tests have been verified.
- [ ] Owner and project manager authorize the public release.

A blocked or skipped check is not a pass. Record the exact commit SHA, environment, command, outcome, and evidence for each manual gate.

## Update and rollback procedure

### Before updating

1. Record the currently installed package version and Git commit.
2. Stop the API and worker processes cleanly; confirm no deployment process is modifying the database.
3. Back up the SQLite database using the project's backup helper and verify its manifest/checksum.
4. Separately preserve the deployment's workflow payload encryption key, provider configuration/secrets, and media asset directory using protected storage. Never commit these materials.
5. Record the application configuration and Python version, without recording secret values.

### Install/update

1. Obtain the reviewed source tag or approved wheel and verify its provenance.
2. Create a fresh virtual environment for the candidate version; do not overwrite the only known-good environment.
3. Install the candidate and its approved dependencies.
4. Review any schema migration instructions before starting the application. Never assume a database downgrade is safe.
5. Start the application in the documented maintenance/upgrade mode, if one exists, and run health and authenticated smoke checks.
6. Start the worker only after the API and database checks succeed.
7. Record the resulting version, commit, and smoke-test outcome.

### Rollback

1. Stop API and worker processes.
2. Restore the previous known-good application environment or reinstall the previous verified artifact.
3. If the candidate changed the database schema or data, restore the matching pre-upgrade database backup to a new path and validate it before switching the application to it. Do not point an older application at a newer schema unless compatibility is explicitly established.
4. Restore the matching encryption key and media assets from their protected backups if they changed.
5. Start the previous version and run health plus authenticated smoke checks.
6. Record the rollback reason and preserve logs without secrets.

The SQLite backup helper validates the database and creates a new restore destination; it does not back up provider tokens, encryption keys, or media files. See [backup and restore](backup-restore.md).

## Evidence and release authority

The Release & Update Manager may prepare branches, changelog entries, packaging improvements, and release documentation. Public release publication, official GitHub Release creation, and final package publication remain under the project owner's and project manager's control.

Never claim cross-platform validation based only on CI. State exactly which operating systems, Python versions, and environments were exercised.
