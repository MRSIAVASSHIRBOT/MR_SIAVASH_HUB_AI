# Windows Local Acceptance Checklist

This checklist is intended for the project owner to run later on a real Windows laptop. It is a manual acceptance gate, not a substitute for CI. Do not mark Windows release acceptance complete until the observed results are recorded against an exact commit SHA.

## 0. Safe test setup

- [ ] Record the exact Git commit SHA under test.
- [ ] Use a dedicated test checkout and a disposable test database; do not point tests at a production or personal database.
- [ ] Keep API tokens, encryption keys, passwords, and provider credentials out of screenshots, terminal transcripts, issue comments, and Git.
- [ ] Confirm Python 3.11 or 3.12 is installed and selected explicitly.
- [ ] Confirm Git and the required Windows build/runtime dependencies are installed.

PowerShell baseline:

```powershell
git rev-parse HEAD
py --list
py -3.11 --version
```

If the project is configured for Python 3.12 instead, use `py -3.12` consistently.

## 1. Clean environment and installation

- [ ] Create a fresh virtual environment in the test checkout.
- [ ] Upgrade pip and install the project with development dependencies.
- [ ] Verify imports and CLI/module entry points without copying secrets into commands.
- [ ] Run the documented test and lint commands from the repository root.

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
python -c "import mrhub; print('import-ok')"
```

Record command exit codes and full test summary. A skipped test suite is not a pass.

## 2. Database and migrations

- [ ] Start with a new disposable SQLite database and verify migrations apply successfully.
- [ ] Restart the application and confirm migrations are idempotent.
- [ ] Upgrade a copy of a prior-version test database.
- [ ] Verify owner authentication, tasks, workflows, approvals, and content records remain readable.
- [ ] Confirm a database/schema failure makes readiness fail closed rather than silently recreating or overwriting data.

## 3. API and worker runtime

- [ ] Start the API using the documented local command and confirm it binds to loopback by default.
- [ ] Check `/health` and `/ready`; record status codes and response fields without exposing tokens.
- [ ] Start the worker as a separate process against the same test database and required encryption configuration.
- [ ] Verify worker heartbeat and queue summary become healthy.
- [ ] Queue a harmless local test job, observe its lifecycle, and confirm it reaches the expected terminal state.
- [ ] Stop the worker gracefully and verify it stops claiming new work.
- [ ] Restart the worker and verify safe recovery behavior.
- [ ] Activate the emergency stop and verify new Agent inference/tool dispatch and new worker claims are blocked; clear the stop only through the documented operator path.
- [ ] Confirm an already in-flight provider call is treated as cooperative cancellation, not falsely reported as forcibly interrupted.

## 4. Agent, memory, and knowledge

- [ ] Verify owner-scoped memory and knowledge retrieval returns only the authenticated owner's records.
- [ ] Verify the complete serialized evidence block respects its configured character budget.
- [ ] Verify retrieved passages are labeled untrusted and cannot grant tool permissions or override policy.
- [ ] Verify source references, hashes, and freshness labels are preserved.
- [ ] Verify no provider silently falls back between local and remote modes.
- [ ] Verify tool schemas and policy authorization are enforced independently of model output.

## 5. Workflow and recovery

- [ ] Run a harmless workflow through queued, running, and terminal states.
- [ ] Test cancellation before dispatch and cooperative cancellation during execution.
- [ ] Verify stale worker leases cannot write checkpoints or terminal states after losing ownership.
- [ ] Simulate an ambiguous external side-effect result only with a mock/test adapter; confirm it enters reconciliation-required state and is not blindly retried.
- [ ] Verify restart recovery does not duplicate completed local steps.

## 6. Backup and restore

- [ ] Back up the disposable test database using the documented helper.
- [ ] Verify manifest, byte size, checksum, and SQLite integrity.
- [ ] Restore to a new path; never overwrite the source or an existing destination.
- [ ] Start the application against the restored database and verify owner login and a protected API read.
- [ ] Separately verify the documented backup/restore procedure for media and required encryption keys; SQLite backup alone does not include these.
- [ ] Confirm the restored database and matching key material can read encrypted queued workflow payloads, using only disposable test data.

## 7. Media and publishing integrations

- [ ] Verify local media upload, metadata, retrieval, and cleanup with harmless test assets.
- [ ] Verify Telegram publishing only against an explicitly configured test destination.
- [ ] Do not attempt live Instagram publishing until the approved public-media hosting adapter, professional account permissions, and provider configuration are in place.
- [ ] For any approved provider test, use one controlled test asset, verify the provider-side result manually, and reconcile ambiguous outcomes before any retry.
- [ ] Confirm tokens and provider diagnostics never appear in logs or API errors.

## 8. Desktop packaging and operational behavior

- [ ] Verify the documented Windows start/stop process works from a clean login session.
- [ ] Verify paths containing spaces and non-ASCII characters are handled correctly.
- [ ] Verify restart after a normal shutdown and after a simulated process crash.
- [ ] Verify application data is stored outside the source checkout in the documented user-data location.
- [ ] Verify upgrade preserves user data and provides a documented rollback path.
- [ ] Verify uninstall does not silently delete user data or backups.

## 9. Evidence and acceptance record

Record:

- Commit SHA:
- Windows edition and build:
- Python version:
- Test date:
- CI run links:
- Installation result:
- Migration/upgrade result:
- API/worker result:
- Agent/memory/knowledge result:
- Workflow/recovery result:
- Backup/restore result:
- Media/provider result:
- Packaging/upgrade/rollback result:
- Failed checks and attached sanitized logs:

**Pass rule:** every applicable check must pass, or be explicitly marked blocked with its reason and owner. Do not claim Windows release acceptance from CI alone. Never attach secrets, private user content, or live credentials to the acceptance record.
