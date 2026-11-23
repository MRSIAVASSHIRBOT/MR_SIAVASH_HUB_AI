# AWI review-summary export

The review-summary exporter emits a bounded, schema-versioned JSON envelope with deterministic serialization and a SHA-256 checksum. The checksum supports integrity comparison when a summary is handed between components.

Input constraints include a positive revision number, a lowercase SHA-256 plan digest, an explicit boolean review decision, at most 500 findings, at most 500 characters per finding, and a maximum serialized UTF-8 payload size of 100 KB.

The checksum is not a digital signature, authentication mechanism, or authorization decision. The exporter does not persist records, approve revisions, authorize tools, or execute workflow steps.
