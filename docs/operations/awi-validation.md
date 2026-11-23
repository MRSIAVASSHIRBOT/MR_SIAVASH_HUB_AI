# AWI plan consistency validator

The read-only `validate_plan` routine reports structural findings for bounded plans: duplicate IDs, malformed step fields, unknown/self/duplicate dependencies, and cycles.

Reports remain review-oriented: `execution_permitted` is always false and human review remains required. This is not policy enforcement or execution authorization.
