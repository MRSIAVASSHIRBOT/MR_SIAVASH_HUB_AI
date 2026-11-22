# Operational Capability Framework — Hub Integration

**Status:** Design/implementation requirements. These capabilities are goals, not a claim that every item exists in runtime today.

This repository is the central execution/control platform for the ecosystem's shared capabilities. Framework names and behaviors are preserved from the owner's collaboration system and translated into implementation contracts.

## Capability framework

- **AWI — Autonomous Workflow Intelligence:** Goal understanding → context gathering → task decomposition → dependency and risk analysis → tool/provider selection → authorized execution → result evaluation → verification → correction/recovery → completion detection. Use bounded workflows, cancellation, checkpoints, retries and durable state where appropriate.
- **GPI — Goal-to-Prompt Intelligence:** Convert plain, incomplete, ambiguous or non-technical requests into structured work orders: intent, scope, context, assumptions, constraints, dependencies, plan, tool requirements, acceptance criteria, verification steps and deliverable. Resolve safe ambiguity using available context; ask only for material decisions.
- **CGI — Capability Gap Intelligence:** Before and during a task, detect missing knowledge, tools, access, provider, environment, dependencies, data or validation. Distinguish confirmed gaps from assumptions; find permitted alternatives, research or remediation; surface blockers accurately.
- **PAIOS — Project/AI Operating System:** Coordinate task state, project priorities, goals, memory, knowledge, tool registry, policy, orchestration, QA, security, integration, continuity and reporting. This is an operating layer, not an unbounded autonomous shell.
- **Evidence and self-evaluation:** Inspect outputs and exact versions, run relevant tests, review diffs, compare acceptance criteria, detect regressions and correct when safe. Report only evidenced results.
- **Uncertainty/research:** Identify claims that need fresh research or repository evidence; cite sources where appropriate; never fabricate unavailable data or claim certainty.
- **Project control and continuity:** Maintain priorities, dependencies, blockers, milestones, decision history and next actionable items. Use repository goals and living project state; do not treat stale memory as code status.
- **Tool intelligence:** Select the least-privileged relevant tool; check capability/access gaps; respect scope, budgets, timeouts and policy; use alternatives only when authorized.
- **Security/privacy:** Least privilege, explicit data scopes, secret protection, sanitized logs, safe defaults, approval boundaries, revocation, auditability and fail-closed authorization.

## Implementation direction
Build shared typed contracts and modules instead of per-feature duplications: task/work-order schema, capability/tool registry, workflow planner/executor, context/memory resolver, policy and risk evaluator, gap detector, evidence/quality evaluator, event/audit record, recovery and status reporter. Keep each layer deterministic and testable; model output is an untrusted proposal.

## Acceptance targets
- Structured requests carry constraints, dependencies and acceptance criteria.
- Tool selection is scoped and policy-checked; no hidden escalation.
- Workflow state is durable and recoverable where tasks need it; retries are bounded and idempotent.
- Gaps/blockers and uncertainty are represented explicitly.
- Self-evaluation produces test/evidence records and actionable corrections.
- Public/private/device-local data scopes are enforced by contracts.
- Cross-project integrations use versioned authenticated interfaces, not direct DB access.
- A completion claim is backed by verification evidence.
