# Evidence-Driven Workflow Evaluation and Correction

## Evaluation

The deterministic evaluator classifies structured acceptance criteria as:

- `passed`: requires a valid SHA-256 digest for the supporting evidence.
- `failed`: requires a valid SHA-256 digest for the failure checkpoint.
- `unknown`: carries no evidence digest and is never counted as passed.

A report is accepted only when every criterion passed. Any failure rejects the evaluation; otherwise any unknown criterion requires review. A missing or malformed evidence digest is an input error, not a pass.

The current durable workflow runner evaluates tool-step completion using persisted status and output/failure digests. Its scope is deliberately reported as `tool_execution_only`; successful tool calls do not prove that the user's end-to-end business goal or every natural-language acceptance criterion was met.

## Correction plan

`build_correction_plan` converts the report into bounded, deterministic recommendations:

- Failed criteria produce a high-priority repair recommendation and require replanning before a retry.
- Unknown criteria produce an evidence collection or reconciliation recommendation. Ambiguous external side effects must not be blindly replayed.
- An accepted report produces no correction actions.

The workflow runner attaches this plan to the persisted tool-outcome evaluation result. The correction planner itself is pure: it does not mutate workflow state, execute tools, grant permissions, request approval or retry a task.

## Limitations

Recommendations are templates, not root-cause diagnosis. The current scope does not yet evaluate the complete GPI WorkOrder acceptance criteria end-to-end because the typed AWI-to-workflow execution bridge remains a proposed design. A future plan-revision service must preserve the original goal, dependency graph, stable step identities, policy checks and idempotency boundaries.
