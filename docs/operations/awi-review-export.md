# Review summary export

The exporter emits a bounded schema-versioned JSON envelope with deterministic serialization and a SHA-256 checksum for integrity comparison during handoff.

The checksum is not a signature, authentication mechanism, or tamper-proof storage. This utility does not persist records or authorize actions.
