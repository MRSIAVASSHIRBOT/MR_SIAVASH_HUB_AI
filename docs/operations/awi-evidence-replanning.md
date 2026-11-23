# AWI evidence gap detection and advisory replanning

The `mrhub.agents.replanning` module accepts a structured evaluation report and
identifies failed and unverified acceptance criteria.

- **Failed**: the report has a failure status and evidence digest; review that evidence before changing the plan.
- **Unverified**: evidence is absent; collect evidence rather than assuming failure.
- **Passed**: omitted from the gap list.

This module is deterministic and advisory. It does not invoke a model, tools,
workflow execution, retries, network requests, or approvals. It returns generic
review recommendations. Future orchestration must preserve explicit policy and
approval checks before executing a revised plan.
