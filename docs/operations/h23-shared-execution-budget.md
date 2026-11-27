# H23 — Shared Agent Execution Budget

- **Status:** Implementation branch opened; PR and exact-head verification pending.
- **Owner:** `MR_SIAVASH_HUB_AI`
- **Expanded phase:** H23 Resource & Budget Management
- **Related compact phases:** H7 execution, H8 recovery, H13 model routing, H18 performance, H20–H22 agent orchestration
- **Branch:** `feat/h23-shared-agent-budget`

## Problem

The HUB model-driven orchestrator already bounded a single run by runtime, input characters, output tokens per request, tool calls, turns and specialist delegations. Those limits were partly local to each orchestrator invocation. A delegated specialist could therefore receive its own input accounting and provider output allowance rather than consuming one shared root-run budget.

A maximum per provider call is not the same as a maximum for the entire parent/child execution tree.

## Implementation in this branch

- A shared `ExecutionBudget` is created once for the root run and passed to every delegated specialist.
- Root and child prompts debit the same total input-character budget.
- Each provider call reserves from the same total output-token budget before inference.
- Reported provider token usage reconciles the reservation and refunds unused reserved capacity.
- When output usage is unavailable, the full reservation is charged conservatively.
- Provider usage above the reservation is rejected before parsing or acting on the response.
- Model calls, tool calls and specialist delegations use shared global ceilings.
- Child agents use the same absolute monotonic deadline as the root run.
- Every result exposes aggregate resource usage metadata without adding prompt contents or secrets.

## Current bounded defaults

| Resource | Limit |
|---|---:|
| Root wall-clock budget | Up to 30 seconds |
| Total model input | Up to 64,000 serialized prompt characters |
| Output per provider call | Up to 512 tokens through the current Agent API |
| Aggregate output reservation | Up to 4,096 tokens |
| Model calls across root and children | 11 |
| Successful tool calls across root and children | Up to 5 |
| Specialist delegations | Up to 2 |
| Specialist recursion | Not enabled |

The values are safety ceilings, not estimates of cost or guaranteed provider billing limits. Input characters are a deterministic preflight bound, not a tokenizer-based token count. Provider-reported output tokens are used when available; missing usage is charged at the full reservation.

## Added regression coverage

1. Parent and delegated specialist share a single output-token budget; child use reduces the parent's next request allowance.
2. Parent aggregate input usage includes the child prompt.
3. A provider reporting more output tokens than reserved cannot return an accepted answer or initiate tool execution.
4. Missing provider usage is conservatively charged at the full output reservation.

## Acceptance still required

- CI on the exact branch head, including Backend CI, general CI, security scans and Windows/video integration workflows.
- Review of the budget contract and actual provider usage behavior.
- Post-merge exact-main CI.
- Extension of the same accounting to durable job workers, external API quotas, compute/storage costs and cross-product accounting.
- Representative load and fairness tests before H23 can be declared DONE.

This change does not claim token billing accuracy, hard interruption of arbitrary synchronous provider code, or a complete cross-product cost-accounting system. External provider adapters still need to honor their own timeout contracts.
