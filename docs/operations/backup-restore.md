# Local SQLite Backup and Restore

The `mrhub.operations.backup` module provides explicit, local-only SQLite backup and restore helpers. It does not run automatically and never overwrites an existing destination.

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
