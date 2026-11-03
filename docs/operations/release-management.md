# Release management and readiness

This document defines the repeatable release process for MR_SIAVASH_HUB_AI.
It is an operational policy and evidence ledger, not a claim that a release is
currently ready.

## Repository baseline reviewed on 2026-11-03

| Area | Observed state | Release implication |
|---|---|---|
| Default branch | `main`, at `f9ef2bc8344369ceb033ecfd4d8b8fa50df9caa7` during this review | Release candidates must be rebased/revalidated against the then-current main head. |
| Branch inventory | More than 100 branches were returned on the first search page; a continuation cursor was present | Branch cleanup requires a complete paginated inventory and owner review; no branches were deleted. |
| Pull requests | PR #104 is this release-management change; PR #101 is a draft Windows acceptance checklist | Neither PR is treated as merged. |
| Version metadata | `0.1.0` in `pyproject.toml` | Current development metadata only; it does not prove a public release exists. |
| Tags and Releases | Git tag refs query returned an empty list; GitHub Releases API returned `[]` | No existing release tag or published GitHub Release was found at review time. |
| Python support | `requires-python = ">=3.11"` | Python 3.11 is the declared floor; there is no declared upper bound. |
| CI Python matrix | Python 3.11 and 3.12 in `.github/workflows/ci.yml` | These are tested on `ubuntu-latest`; no Windows or macOS runner is configured. |
| Backend CI | Python 3.11; dependency audit, Ruff, pytest | This workflow is a separate check from the packaging smoke test. |
| Build backend | Setuptools (minimum `84.1.0`) with `wheel` | The package is built as a Python wheel from `backend/`. |
| Runtime dependencies | FastAPI, Uvicorn, Pydantic, pydantic-settings, HTTPX, cryptography | Direct dependencies use bounded version ranges, not exact pins. |
| Development dependencies | pytest, Ruff, pip-audit, Bandit | Bandit is pinned to `1.9.4`; the other development tools use ranges. |
| Dependency lock | No root `uv.lock`, `poetry.lock`, `requirements.txt`, or `requirements-dev.txt` was present in the root listing | Transitive resolution is not locked for repeatable deployment installs. Adopt one canonical lock workflow before promising deterministic installs. |
| Install path | README documents `python -m pip install -e ".[dev]"` for development | A separate production install/upgrade guide is still needed for operators installing a built wheel. |
| Wheel contents | CI checks `mrhub/web/index.html`, `app.css`, and `app.js` are present | Required UI assets are explicitly checked in the wheel. |
| Database migrations | `SchemaMigrator` contains ordered, checksummed, transactional SQLite migrations through version 18 | Forward migration and integrity checks exist; there is no general downgrade migration path. Use a verified pre-upgrade backup for rollback. |
| Backup/restore | Local SQLite helper creates a checksum manifest, checks SQLite integrity, and refuses to overwrite destinations | It covers the SQLite database only, not encryption keys, provider credentials, or media assets. |
| License | README says license selection is pending; no root `LICENSE` file was found | Resolve the project's distribution license before publishing a public package. |
| Windows acceptance | PR #101 is a draft with a detailed real-device checklist | Windows remains unverified until the owner completes and records the checklist on a real Windows machine. |

## CI evidence for the release-management PR

The following workflows completed successfully on PR #104 head commit
`fc2fee6c23dff5d7eb26993d779ab36358f6b393`:

- [CI run 822](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_HUB_AI/actions/runs/41544031172): Python 3.11 and 3.12 jobs passed, including pytest, wheel build, packaged UI asset verification, clean virtual-environment wheel installation, and the `/health` smoke test.
- [Backend CI run 1032](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_HUB_AI/actions/runs/41544031145): dependency audit, Ruff, and pytest steps passed on Python 3.11.
- [Defensive Python Scan run 9](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_HUB_AI/actions/runs/41544031144): Bandit scan step completed successfully.

These are Linux GitHub-hosted runner results for that exact PR head. They do not establish Windows/macOS compatibility or acceptance of a later commit.

Issue [#66](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_HUB_AI/issues/66) originally recorded failures before runner assignment. The successful runs above satisfy its stated acceptance condition (nonzero runner, executed steps, completed result); retain the issue history as infrastructure context rather than treating those earlier failures as application test failures.

A local clone/build could not be run in this execution environment because outbound DNS resolution for `github.com` was unavailable. No local Windows device or macOS environment was available.

## Semantic Versioning policy

Use `MAJOR.MINOR.PATCH`:

- **MAJOR**: an incompatible public API, configuration, data, or operational contract change.
- **MINOR**: backward-compatible functionality or a new supported capability.
- **PATCH**: backward-compatible bug fixes, security fixes, and packaging/documentation corrections.

Until the project declares a stable 1.0 API, use `0.y.z` with care: under SemVer, anything may change before 1.0. Document breaking changes explicitly.

The version in `pyproject.toml`, the release tag (`vX.Y.Z`), and the GitHub Release title must match. Do not create or publish a tag from an unreviewed or unvalidated commit. Never overwrite an existing release tag.

## Dependency and build policy

1. Keep direct runtime and development dependencies declared in `pyproject.toml`.
2. Review direct and transitive dependency changes for Python compatibility, license, maintenance status, known vulnerabilities, and platform-specific wheels.
3. Run `pip-audit --skip-editable` against the resolved environment and retain the result for the exact release commit.
4. The current version ranges are not a complete dependency lock. Adopt one canonical lock strategy (recommended: committed `uv.lock` and documented uv commands) before claiming deterministic deployment resolution. Do not maintain multiple competing lock sources.
5. Build a wheel and inspect it; verify all runtime package data, including `mrhub/web/index.html`, `mrhub/web/app.css`, and `mrhub/web/app.js`.
6. Install the built wheel into a fresh environment outside the source tree and perform an import and health smoke test.
7. Resolve the distribution license before publishing any package publicly.

## Release gates

A release candidate must satisfy all applicable gates:

- [ ] The release commit is based on the intended, reviewed branch head.
- [ ] Version metadata, tag name, changelog, and release notes agree.
- [ ] Full CI completes on the exact candidate commit, with actual runner assignment, steps, and logs.
- [ ] Python 3.11 and 3.12 test matrix passes.
- [ ] Dependency audit and lint pass; findings are reviewed and dispositioned.
- [ ] Wheel builds successfully and required UI assets are present.
- [ ] Clean wheel installation and application health smoke test pass.
- [ ] One canonical dependency lock is committed and install instructions use it.
- [ ] The distribution license is selected and included.
- [ ] Database schema/migration behavior is reviewed; forward-only migration and rollback limitations are documented.
- [ ] Backup and restore are tested against a disposable copy; encryption keys and media assets are handled separately.
- [ ] Windows real-device acceptance is recorded when Windows is a supported target. Linux CI is not a substitute.
- [ ] macOS is either explicitly supported and tested or clearly listed as unsupported/not validated.
- [ ] External integrations remain disabled unless credentials, network reachability, and controlled acceptance tests have been verified.
- [ ] Owner and project manager authorize the public release.

A blocked or skipped check is not a pass. Record the exact commit SHA, environment, command, outcome, and evidence for each manual gate.

## Database migration and rollback policy

The current SQLite schema uses ordered migrations recorded in `schema_migrations`. Each migration has a version, name, and SHA-256 checksum. Migrations execute in transactions; the migrator rejects unknown future versions, out-of-order history, and checksum drift. Tests cover fresh initialization, idempotent re-entry, legacy row preservation, checksum mismatch, and failed-migration rollback.

There is no general reverse-migration engine. Treat schema changes as forward-only unless a specific, reviewed reverse operation is supplied. For rollback after a migration has changed schema or data, restore the matching pre-upgrade database backup to a new path, validate it, then switch the previous application version to that restored database. Never point an older application at a newer schema without explicit compatibility evidence.

## Update procedure

### Before updating

1. Record the installed package version, Git commit, Python version, and sanitized configuration inventory.
2. Stop API and worker processes cleanly; confirm no process is writing to the database.
3. Back up the SQLite database using the project's backup helper and verify its manifest, byte size, checksum, and SQLite integrity result.
4. Separately preserve the workflow payload encryption key, provider configuration/secrets, and media asset directory using protected storage. Never commit these materials or include secret values in a manifest.
5. Preserve the previous known-good wheel/source artifact and virtual environment until acceptance completes.

### Install/update

1. Obtain the reviewed source tag or approved wheel and verify its provenance.
2. Create a fresh virtual environment for the candidate; do not overwrite the only known-good environment.
3. Install the candidate and dependencies from the approved lock workflow.
4. Review pending database migrations and release notes before starting the application.
5. Start the application against a disposable copy first; verify schema version, `/health`, `/ready`, and authenticated smoke checks.
6. Start the worker only after API and database checks succeed.
7. Record resulting version, commit, migration versions, and smoke-test outcome.

### Rollback

1. Stop API and worker processes.
2. Restore the previous known-good application environment or reinstall the previous verified artifact.
3. If schema/data changed, restore the matching pre-upgrade database backup to a new path and validate it before switching the application to it.
4. Restore matching encryption key material and media assets from their protected backups if they changed.
5. Start the previous version and run health plus authenticated smoke checks.
6. Record the rollback reason and preserve sanitized logs.

The SQLite helper does not back up provider tokens, encryption keys, or media files. See [backup and restore](backup-restore.md).

## Evidence and release authority

The Release & Update Manager may prepare branches, changelog entries, packaging improvements, and release documentation. Public release publication, official GitHub Release creation, final package publication, and final tag creation remain under the project owner's and project manager's control.

Never claim cross-platform validation based only on CI. State exactly which operating systems, Python versions, and environments were exercised.


## Superseding integration baseline — 2026-11-04 UTC

This section supersedes the older repository/migration snapshot above. The current main commit is
`a5a1002907b3ddac2b218b84312e2fd74f2d0256`, created by merging PR #223.

The exact PR head `fe153ac1d9a3b57e3a3e836c54e262263b36626c` passed:
- Backend CI (dependency audit, Ruff and backend tests).
- CI on Python 3.11 and 3.12 (test suite, wheel/package verification and lint).
- Defensive Python Scan.
- Real FFmpeg/FFprobe MP4 integration on Ubuntu and Windows hosted runners.

The merge commit's post-merge push workflows were still running at the time of this update, except Defensive Python Scan, which passed. Do not treat exact PR-head CI as a substitute for post-merge main CI; re-check the push runs on the exact main SHA.

### Updated implementation and release implications

- SQLite schema migrations now extend through version 27.
- The backup/restore documentation now includes a coordinated database/media/key recovery procedure and a bounded read-only media integrity verifier. The verifier checks generated storage keys, file presence, size and SHA-256 without copying or deleting files. It is a consistency gate, not a backup utility or a restore drill.
- Video rendering now has durable owner-scoped jobs, idempotency, lease-fenced worker execution, reserved output keys, atomic output registration, source media-use leases and stale orphan cleanup.
- Real renderer execution was verified on Linux and Windows hosted CI. This does not establish target-device acceptance, production performance or clean Windows installation.
- The renderer currently produces silent hard-cut-only MP4. Audio, transitions, captions, graphics and AI-generated footage remain outside the implemented contract. No AI video provider adapter is registered.

### Release decision

The project remains **not release-ready**. Outstanding gates include the actual target Windows device acceptance, coordinated restore drill (including protected key material and media), clean install/upgrade/rollback, dependency lock and license decisions, external provider/social integration acceptance, and a complete product-level operator workflow. No public release, tag or package publication is implied by the PR #223 merge.
