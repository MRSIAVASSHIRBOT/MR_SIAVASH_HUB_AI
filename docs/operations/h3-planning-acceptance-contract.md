# H3 — Goal-to-Prompt and Agent Planning Acceptance Contract

Status: acceptance contract; not a claim that every stage is integrated.
Existing foundations/active work include typed WorkOrders, deterministic preflight goal analysis, bounded dependency-aware AWI plans, capability-gap assessment, plan revisions, consistency validation, digest-bound review/integration previews, and bounded replanning.

## Planning pipeline
1. **Goal normalization**: preserve the user's goal; bounded input; normalize whitespace and Persian/Arabic variants without changing intent.
2. **Goal analysis (GPI preflight)**: explain complexity, required modalities, research signal, tool-use signal, information gaps, and clarification signals. Deterministic heuristic results are advisory.
3. **WorkOrder generation**: produce intent, scope, assumptions, constraints, dependencies, capabilities, acceptance criteria, verification steps. Server owns risk classification; model risk is ignored.
4. **WorkOrder validation**: strict schema, bounds, nonblank text, unique/normalized identifiers where defined; prohibited goal screening before provider selection where possible.
5. **Capability assessment**: compare requested capabilities against registered catalog only. Missing capability is explicit; catalog presence does not imply authorization.
6. **AWI plan**: bounded DAG with unique stable step IDs, valid dependency graph, exact criterion/capability coverage, rationale, and verification definition.
7. **Plan consistency**: validate structural and semantic relationships without executing tools or changing permissions.
8. **Revision proposal**: preserve completed stable identities, bind proposal to prior/candidate digest, reject invalid dependencies and no-progress loops.
9. **Review**: record explicit owner/reviewer decision bound to exact revision digest; approval is not execution authorization.
10. **Handoff**: any future execution bridge revalidates policy, grants, approval, input, idempotency, and tool schemas at execution time.

## Planning invariants
- The user's original goal remains authoritative; model output cannot rewrite it.
- Planning artifacts are data, not commands, credentials, or permissions.
- Planning and capability assessment never invoke handlers.
- Model-provided risk classification is ignored.
- Missing required capability is reported; never hallucinated as registered.
- Plan steps are declarative and bounded; no shell snippets, raw credentials, or arbitrary executable payloads.
- Dependencies are acyclic, unique, refer only to known step IDs, and deterministic.
- Every required acceptance criterion and declared capability is covered exactly; no undeclared requirement is added silently.
- Replanning is bounded and stops on no-progress, repeated digest, invalid plan, or review refusal.
- Candidate changes require digest-bound review; changed content invalidates prior approval.
- Authorization and execution readiness are independently computed server-side.

## Test acceptance matrix
- Original goal preserved through generated WorkOrder and analysis.
- Invalid/oversized goal blocked before provider selection.
- Prohibited goals rejected before provider invocation.
- Model-supplied risk and extra fields ignored/rejected.
- WorkOrder schema rejects blanks, duplicates, excessive fields, invalid capability names, and unsupported values.
- Capability report distinguishes registered, missing, and permission/authorization-not-checked.
- Plan rejects duplicate IDs, unknown/self/repeated dependencies, cycles, excessive steps, missing/extra criteria, and missing/extra capabilities.
- Planning is read-only: no tool calls, permissions changed, execution started, or side effects.
- Revision preserves completed steps and rejects stale digest, tampering, invalid graph, and no-progress.
- Review binds to exact revision digest and actor.
- Replanning budget enforced; exhaustion produces safe terminal/review state.
- API owner scoping, auth, sanitized errors, and audit failure behavior verified.

## Known limitation
Deterministic keyword analysis is a heuristic and cannot fully understand intent or risk. Capability presence does not prove the tool is safe or authorized. Planning artifacts remain review-only until an explicit secure execution bridge is implemented and tested.
