# Local SQLite Backup and Restore

The `mrhub.operations.backup` module provides explicit, local-only SQLite backup and restore helpers. It does not run automatically and never overwrites an existing destination.


## Command-line recovery tools

After installing the project, the same guarded operations are available through the `mrhub-db` command:

```text
mrhub-db backup <source.sqlite3> <new-backup.sqlite3>
mrhub-db restore <backup.sqlite3> <new-destination.sqlite3>
mrhub-db verify-backup <backup.sqlite3>
mrhub-db verify-media <database.sqlite3>
```

Each command prints one JSON result for scripts and operator workflows. Backup and restore refuse to overwrite an existing destination. Media verification is read-only; it returns exit code `1` when integrity checks fail. Invalid input, missing manifests, checksum failures, and filesystem errors return exit code `2`. These commands never start the API/worker, alter a live database, copy media, or manage secret material automatically.


## Backup

Call `backup_database(source_path, destination_path)`. The destination database and a `.manifest.json` sidecar are created. The manifest includes the SHA-256 digest, byte size, SQLite integrity result, and a list of data categories deliberately excluded.

## Restore drill

Call `restore_database(backup_path, new_destination_path)`. Restore verifies the manifest, file size, checksum, and SQLite `PRAGMA quick_check` before creating a new destination. Run this drill against a temporary path before relying on a backup.

## Security and limitations

- On POSIX systems, created files are restricted to owner read/write permissions where supported.
- Never store backup files in a public web directory or commit them to source control.
- This module backs up the SQLite database only. Provider tokens, encryption keys, media assets, and other external files require separate protected backup procedures; do not put secrets into the manifest.
- Checksums detect accidental or unauthorized modification only when the manifest is protected separately. They are not a signature or encryption.
- Keep an offline or otherwise isolated copy and periodically test restoration on the target machine.
- A successful SQLite integrity check does not prove the whole application can start or that external integrations work after restore.


## Full local recovery set: database, media, and keys

The application database and the media directory form one logical recovery set. The media repository stores files under:

`<database_path parent>/content_assets/`

The database records the generated storage key, file size, and SHA-256 content hash for each asset. The SQLite helper above does **not** copy this directory.

### Before creating a full recovery point

1. Stop the API and worker cleanly so uploads, transcodes, renders, cleanup jobs, and database writes are quiescent. A SQLite online backup alone does not make a separately copied media directory atomic with the database.
2. Run `backup_database` to create the database file and manifest in a private destination outside the application data directory.
3. Copy the sibling `content_assets/` directory to a separate encrypted backup location. Preserve file names and verify every copied file against the database's `content_assets.storage_key`, `file_size`, and `content_hash` values. Do not follow unexpected symlinks or include files outside this generated asset directory.
4. Record the application version, migration version, backup timestamp, and a count of registered/copied assets in the operator's recovery record. Do not put secrets, tokens, or raw user content into the manifest.
5. Keep the database backup, media backup, and recovery record in an access-controlled offline or otherwise isolated location.

### Key material and provider credentials

These values are not stored in the SQLite backup and must be managed separately:

- `MRH_WORKFLOW_PAYLOAD_KEY`: the 32-byte URL-safe Base64 key used to decrypt durable encrypted workflow payloads. Losing it makes existing encrypted workflow payloads unrecoverable. Preserve it in a password manager or dedicated secret manager with an independent recovery path.
- `MRH_PUBLIC_MEDIA_SIGNING_KEY`: used to sign short-lived public media URLs. If it is rotated or lost, previously issued signatures stop validating; issue new URLs after restore.
- Provider credentials such as `MRH_REMOTE_INFERENCE_API_KEY`, `MRH_TELEGRAM_BOT_TOKEN`, and `MRH_INSTAGRAM_ACCESS_TOKEN`: provision or rotate these through the relevant provider/secret manager after restore. Do not bundle them into the database or media archive.

Never commit `.env`, raw keys, access tokens, private certificates, or recovery codes to GitHub. Do not print secrets into logs or support reports.

### Restore order and verification

1. Keep the API and worker stopped. Restore the SQLite database to a new destination with `restore_database`; never overwrite the only copy of the live database.
2. Restore `content_assets/` as a sibling of the restored database file. Verify each registered asset's existence, size, and SHA-256 content hash before starting the service. Missing or mismatched files must be reported; do not silently delete their database records.
3. Restore `MRH_WORKFLOW_PAYLOAD_KEY` from the independent secret store before starting any worker that may process encrypted workflow payloads. Re-provision provider credentials separately. Reconfigure the public-media signing key and base URL; assume previously issued signed URLs may need to be regenerated.
4. Start the API in loopback-only mode and verify health, owner login, asset listing, and authenticated media download. Then start the worker and verify readiness and a controlled, non-side-effecting workflow recovery check.
5. Run migration/integrity checks and record the restored application version, database migration version, asset verification totals, and any unavailable external providers.

### Recovery acceptance record

A recovery drill is **ACCEPTED** only when the operator records:
- backup timestamp and exact application commit/version;
- database manifest checksum and SQLite integrity result;
- registered media count, copied media count, and verified hash count;
- confirmation that the workflow payload key was recovered without exposing it;
- API/worker startup and owner-login results;
- any provider that remains intentionally disabled or requires reauthorization.

This procedure is a runbook design. It has not yet been exercised on the owner's Windows device; do not label it runtime-verified until that drill is performed.

## Read-only media integrity verification

Before copying the media directory for a coordinated recovery point, run
`verify_media_assets(database_path)` from `mrhub.operations.backup` while API
and worker writers are stopped. It compares every registered asset's generated
storage key, file size, and SHA-256 digest with the sibling `content_assets/`
file. It also reports missing files, mismatched size/hash, invalid or symlinked
entries, and unregistered directory entries as aggregate counts only; it never
returns storage keys or file contents and never copies or deletes files.

A backup set should not be accepted while the verifier reports `ok: false`.
This verifier is a local consistency gate, not a media backup/copy utility and
not a substitute for an actual restore drill. Verification is bounded to 10,000 registered assets, 10,000 directory entries, and 100 MB per asset; larger registries or implausible metadata fail closed and require an explicitly planned offline verification procedure. The API and worker must remain
quiescent while the database and media directory are checked and copied, so the
two components represent the same recovery point.

## Automated clean-destination recovery regression

The automated suite now exercises a clean-destination recovery path for the database and media directory together: it creates an owner account, uploads a bounded media fixture, closes the source application, backs up and restores SQLite to a new directory, copies the sibling media directory, runs `verify_media_assets`, then starts a fresh application against the restored database and verifies owner login, asset listing, and authenticated byte-for-byte download.

This regression test is automated evidence for the local recovery contract. It does not replace the documented Windows target-device drill, protected recovery-key procedure, encrypted off-device backup, or operator acceptance record.
