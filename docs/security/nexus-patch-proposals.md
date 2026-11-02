# NEXUS Patch Proposal and Diff Review

The authenticated `POST /nexus/patch-proposals` endpoint creates a bounded unified diff from caller-supplied original and proposed Python source text. It reports SHA-256 fingerprints, syntax status for both versions, and the review diff.

## Safety contract

- The `path` field is a relative Python-file label only; the service does not read that path from disk.
- The service does not import or execute either source version and never applies the diff.
- Source and diff sizes are bounded. Unsafe path labels and non-Python labels are rejected.
- Audit events record only a proposal identifier and a fixed reason code; source text and diff contents are not persisted.
- The proposal is returned for immediate review and is not durably stored. A syntax error is reported rather than silently fixed.
- A clean parse is not proof of correctness or security. Review the diff and run tests in a separate isolated environment before considering any change for application.

This is a review primitive, not an autonomous code-modification or execution engine.
