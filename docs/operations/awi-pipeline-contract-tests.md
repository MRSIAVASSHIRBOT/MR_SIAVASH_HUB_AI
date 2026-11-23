# AWI review-pipeline contract tests

The cross-module contract test exercises the proposal-only flow:

1. Convert evaluation gaps into an additive plan revision proposal.
2. Validate the candidate dependency graph.
3. Bind an explicit review decision to the candidate revision digest.
4. Build a read-only integration preview that rejects a changed candidate.
5. Export a bounded review summary with a deterministic checksum.

The contract verifies that validation and preview remain review-only. A valid plan or affirmative review record is not an execution authorization and does not dispatch tools.
