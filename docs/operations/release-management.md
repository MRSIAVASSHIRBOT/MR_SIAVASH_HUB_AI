# Release management and readiness

This document defines the repeatable release process for MR_SIAVASH_HUB_AI.
It is an operational policy and evidence ledger, not a claim that a release is
currently ready.

> Historical evidence is retained below for traceability. The dated superseding baselines later in this document take precedence wherever repository state has changed.

## Historical repository baseline reviewed on 2026-11-03

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

All four post-merge push workflows passed on the exact main commit `a5a1002907b3ddac2b218b84312e2fd74f2d0256`: Backend CI run `41722222701`, CI run `41722222754`, Defensive Python Scan run `41722222735`, and Video Render Integration run `41722222736`. These are hosted CI results, not target-device acceptance.

### Updated implementation and release implications

- SQLite schema migrations now extend through version 27.
- The backup/restore documentation now includes a coordinated database/media/key recovery procedure and a bounded read-only media integrity verifier. The verifier checks generated storage keys, file presence, size and SHA-256 without copying or deleting files. It is a consistency gate, not a backup utility or a restore drill.
- Video rendering now has durable owner-scoped jobs, idempotency, lease-fenced worker execution, reserved output keys, atomic output registration, source media-use leases and stale orphan cleanup.
- Real renderer execution was verified on Linux and Windows hosted CI. This does not establish target-device acceptance, production performance or clean Windows installation.
- The renderer currently produces silent hard-cut-only MP4. Audio, transitions, captions, graphics and AI-generated footage remain outside the implemented contract. No AI video provider adapter is registered.

### Release decision

The project remains **not release-ready**. Outstanding gates include the actual target Windows device acceptance, coordinated restore drill (including protected key material and media), clean install/upgrade/rollback, dependency lock and license decisions, external provider/social integration acceptance, and a complete product-level operator workflow. No public release, tag or package publication is implied by the PR #223 merge.


### Post-merge verification update — 2026-11-04 UTC

All push-triggered workflows on main commit `a5a1002907b3ddac2b218b84312e2fd74f2d0256` completed successfully: Backend CI, CI, Defensive Python Scan and Video Render Integration. This confirms the merged baseline remains green after integration; it does not replace target-device acceptance or the coordinated restore drill.


## Superseding release baseline — 2026-11-04 (post-PR #227)

Current main is `fabafbad607aa6bcf254669a3ccb1b4b7ff9ce2d`. PR #227 integrated the RTL operator controls for video render submission, manual status refresh, queued/running cancellation and authenticated MP4 download. The media library also supports authenticated asset downloads. Render submission uses a per-analysis idempotency key persisted in the current tab session to protect uncertain retries.

The exact PR #227 head `643ddfaf141004f19a90067f0992d60cebce564a` passed Backend CI, Python 3.11/3.12 CI, Defensive Python Scan, and real FFmpeg/FFprobe integration on Linux and Windows. All four post-merge push workflows on main `fabafbad607aa6bcf254669a3ccb1b4b7ff9ce2d` also passed (Backend CI run 41724900988, CI run 41724901109, Defensive Python Scan run 41724900883, Video Render Integration run 41724900921).

The UI does not start background polling; the pull Worker must be running separately. Downloads use authenticated same-origin requests, omit ambient cookies, do not place bearer tokens in URLs, and enforce the 100 MB client-side bound. The renderer still produces silent hard-cut-only MP4. No audio, transitions, captions, graphics, AI-generated footage or operational AI video provider is claimed.

### Updated release decision

The project remains **not release-ready**. Remaining gates include target-device Windows installation and real-media acceptance, browser/UX acceptance, coordinated database/media/key restore drill, clean upgrade/rollback, canonical dependency lock, license decision, external provider/social acceptance and final owner approval. No public tag, release or package publication is implied by these merges.


## Current release-manager baseline — 2026-11-04 17:42 +0330

**Observed main commit:** `6e0a41a52c5a9f28faaa9b5ffb15b971e1bbffd2`  
**Repository default branch:** `main`  
**Package metadata:** `0.1.0` (`pyproject.toml`; development metadata, not a published release).  
**Recently merged release-relevant work:** PR [#276](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_HUB_AI/pull/276) merged as `6e0a41a52c5a9f28faaa9b5ffb15b971e1bbffd2`. It closes the stale-snapshot/new-render race for both snapshot-value and snapshot-ID submissions while preserving retries of already accepted idempotent renders. Its exact PR head `8fab7b80f62d6ea666f658fa447c9bdba97eb8a1` passed Python 3.11/3.12, Backend CI, Defensive Python Scan and Linux/Windows FFmpeg integration. A complete successful post-merge set is now recorded on main commit `6e0a41a52c5a9f28faaa9b5ffb15b971e1bbffd2`: CI run `41845994226`, Backend CI run `41845994047` (also `41846328754`), Defensive Python Scan run `41845994201`, and Video Render Integration run `41845993797`. Later duplicate push runs include cancelled or still-running attempts; they do not negate this completed successful set.

### Current packaging and platform facts

- Python metadata still declares `>=3.11`; the standard CI workflow tests Python 3.11 and 3.12 on `ubuntu-latest`. No upper Python bound is declared, and versions above 3.12 are not established by this matrix.
- The standard CI workflow installs editable development dependencies, checks browser JavaScript syntax with Node, runs pytest with coverage, builds a wheel, checks the three packaged web assets, installs the wheel into a fresh Linux virtual environment, and performs a `/health` smoke test.
- Backend CI separately runs `pip-audit --skip-editable`, Ruff and pytest on Python 3.11/Linux.
- The repository has a separate real FFmpeg/FFprobe integration workflow with hosted Linux and Windows coverage. Hosted Windows CI is not equivalent to a clean install and acceptance run on the owner's actual Windows device.
- No root `LICENSE` file was found in the current-main lookup. The project license decision remains unresolved; do not publish a distributable package until it is resolved.
- The current `pyproject.toml` still uses bounded dependency ranges and no canonical lock file was found in the root inventory. A reproducible deployment lock is still an open gate. Do not create a placeholder lock file or claim deterministic resolution without a genuine resolver-generated lock and a clean locked install.
- The previous Windows acceptance PR #101 is now merged as documentation. The authoritative manual checklist is `docs/operations/windows-acceptance-checklist.md`; its existence does not mean the real-device run has been completed.
- SQLite migrations were extended by the merged video snapshot work through versions 28–29. This does not imply a general downgrade engine; rollback remains based on a verified pre-upgrade backup and matching application/key/media state.

### Release-manager action boundaries

PR #276 is merged. The Release & Update Manager records its merge and exact-head CI as release evidence; the post-merge main checks must still complete successfully. Target-device acceptance and the broader release gates remain separate.

### Current release decision

**Not release-ready.** The following are still hard gates: canonical dependency lock and locked installation; license selection; actual Windows device acceptance; coordinated database/media/encryption-key restore drill; clean install/upgrade/rollback; browser/operator acceptance; external provider and social-account acceptance; exact-candidate CI; and explicit owner authorization. No release tag, GitHub Release, or package publication is created by this update.


## Superseding release-manager baseline — 2026-11-08 UTC

This section supersedes the 2026-11-04 release-manager snapshot above. It records the state observed on the exact current `main` commit; PR branch checks are listed separately and are not treated as merged behavior.

**Current main:** `6a5db881c9cacea2b32f2e89b5d62d6f7ef91cf0`  
**Observed mainline delta:** 20 commits since the previously inspected `8f190eeac4b4627692b60ac27e6dd5c12e4557bc`.  
**Package version:** `0.1.0` in `pyproject.toml`; development metadata only.  
**Python declaration:** `>=3.11`; automated full test matrix currently covers 3.11 and 3.12.  
**Tags / GitHub Releases:** current Git tag refs and Releases API both returned empty arrays.  
**Dependency lock / license:** no root `uv.lock` or `requirements.lock` found; no root `LICENSE` found. Both remain hard release blockers.

### Verified mainline integration

The following relevant changes are merged into main:
- PR #276: stale snapshot/new render race fence, with accepted idempotent retries preserved.
- PR #278: release management evidence and readiness documentation refresh.
- PR #311: media scan interruptions now produce an explicit incomplete/truncated verification result.
- PR #308: shared heuristic credential screening is enforced at API and repository persistence boundaries. It is defense-in-depth pattern screening, not a complete secret scanner.

All four required push workflow groups passed on exact main commit `6a5db881c9cacea2b32f2e89b5d62d6f7ef91cf0`:
- Backend CI: [run 42325251955](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_HUB_AI/actions/runs/42325251955)
- CI (Python 3.11/3.12): [run 42325251968](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_HUB_AI/actions/runs/42325251968)
- Defensive Python Scan: [run 42325251978](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_HUB_AI/actions/runs/42325251978)
- Video Render Integration (hosted Linux/Windows): [run 42325252133](https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_HUB_AI/actions/runs/42325252133)

A later duplicate push attempt on the same SHA had a Backend CI run still in progress and a Defensive Python Scan attempt cancelled; it does not erase the separate complete successful four-workflow set above. Re-run all required groups on any future release-candidate SHA.

### Current open PR and workflow inventory

The following branches are not merged and do not alter mainline release behavior:
- **PR #312**, Draft documentation/status refresh: 15 commits ahead / 0 behind current main. All four required exact-head groups passed on `49203ad83d94bbebcce52436cd88d6111c38144c` (Backend CI `42428122021`, CI `42428122030`, Defensive Scan `42428122033`, Video Integration `42428122022`). Keep its Draft state until the project owner/manager accepts its content.
- **PR #310**, Draft authenticated project portfolio: 13 commits ahead / 0 behind. All four required groups passed on exact head `a869fad16242ae9ba949e4e44e8b774cfab5af56` (Backend CI `42325299006`, CI `42325299000`, Defensive Scan `42325298999`, Video Integration `42325299070`). This is a static explicit registry, not live cross-repository or infrastructure monitoring. Keep Draft pending architecture and product acceptance.
- **PR #309**, Draft central control-center ADR: 3 commits ahead / 0 behind. All four required groups passed on exact head `de6a3dbdc1730bbe6f460d8e84a36b7c8aac215d` (Backend CI `42325283920`, CI `42325283936`, Defensive Scan `42325283918`, Video Integration `42325283919`). ADR status remains Proposed; CI success does not accept the architecture decision.
- **PR #297**, workflow payload-envelope formatting/key-load test: 1 commit ahead / 8 behind current main; all four workflow groups are `action_required`. It is not merge-ready. Do not bypass authorization. Reconcile the branch with current main and re-run the full matrix before review.

### Packaging and platform decision

The existing full CI job still runs on Ubuntu with Python 3.11 and 3.12. It builds and installs a wheel in a clean Linux virtual environment. The separate FFmpeg/FFprobe integration has hosted Linux and Windows jobs, but that is not a Windows wheel-install test or a real-device acceptance run.

This update adds a dedicated clean-wheel smoke matrix on Ubuntu and Windows for Python 3.11 and 3.12. For each cell it builds a wheel, verifies the three packaged UI assets, installs the wheel into a fresh virtual environment, and checks `/health`. This provides automated package-install evidence for Windows while keeping actual Windows-device, browser, media workflow, and macOS acceptance as separate gates. The matrix is proposed in the associated PR and is not yet part of main until merged.

### Current release decision

**Not release-ready.** Hard blockers remain: a genuine canonical dependency lock and locked-install proof; a project license decision and included LICENSE file; Windows real-device acceptance; coordinated database/media/encryption-key backup and restore drill; clean install/upgrade/rollback; browser/operator acceptance; external provider and social-account acceptance; exact release-candidate CI; and explicit owner authorization. No tag, GitHub Release, or package publication is created by this work.


### GitHub Actions runtime and pin baseline — 2026-11-08

The release CI refresh pins the following official GitHub Actions to verified Node 24-compatible release commits:
- `actions/checkout` v7.0.1 — `3d3c42e5aac5ba805825da76410c181273ba90b1`.
- `actions/setup-python` v7.1.0 — `6d4fd22b20465ccc0f7354476588e8df7c9ca0e0`.
- `actions/upload-artifact` v7.0.2 — `cf430e030ddbb5b0abf93d22962f4752f3646cd9`.

These pins are applied to the CI, Backend CI, Defensive Python Scan, Video Render Integration, and Windows Launcher Validation workflows. The separate scheduled Continuous Development publisher workflow retains its existing artifact action contract pending a dedicated review of its privileged publish boundary; it is intentionally not changed in this PR.

The wheel health smoke checks use HTTPX `ASGITransport` and `AsyncClient` rather than Starlette's deprecated `TestClient` + HTTPX integration. This avoids suppressing a deprecation warning while retaining an in-process ASGI health check. The exact candidate workflows must verify these changes.
