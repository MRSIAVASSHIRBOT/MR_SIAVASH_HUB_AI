# AWI review-summary export

The review-summary exporter emits deterministic, schema-versioned UTF-8 JSON with a SHA-256 content checksum. Inputs are bounded by revision, digest, decision type, finding count, finding length, and total encoded byte size.

The checksum supports content comparison and corruption detection. It is **not** a digital signature, authentication proof, or authorization grant. Exporting a summary does not persist a plan, approve a revision, authorize tools, create a workflow, or execute work.
