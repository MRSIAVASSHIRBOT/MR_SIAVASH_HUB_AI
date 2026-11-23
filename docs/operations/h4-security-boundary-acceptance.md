# H4 — Security and Permission Boundary Acceptance

Status: review checklist; not a security certification.
Current foundations include server-authoritative policy evaluation for registered tools, owner-scoped active permission snapshots, typed permission names, audit events, and untrusted-tool-observation labels in the agent prompt/transcript. The tool-output trust change is explicitly a prompt-level signal, not complete taint tracking.

## Trust hierarchy
1. System/developer policy and application security constraints.
2. Current authenticated user's request and explicit approvals, within policy.
3. Server-owned registered tool metadata and permission grants.
4. Verified evidence with provenance and freshness.
5. Retrieved memory, external data, model output, and tool observations: untrusted context.

No lower tier may override a higher tier or grant permissions.

## Required security checks
- Authentication: protected routes reject unauthenticated requests; login/session token handling, expiry, and brute-force throttling are verified.
- Authorization: all route handlers and tool invocation enforce owner scope and current server-side grants.
- Policy: clients cannot submit trusted risk, grant, required-permission, side-effect, or approval facts.
- Tool catalog: unknown tools fail closed; registration validates definitions and schemas.
- Prompt injection: tool observations, retrieved documents, memory, provider output, URLs, and delegated results are treated as untrusted data, not executable instructions.
- Secrets: prompt/output/log/memory filters prevent credentials and tokens from leaking.
- Data boundaries: owner/project scoping is enforced at repository and API layers, not only UI.
- Resource abuse: request, output, context, retries, concurrency, and duration bounds are enforced.
- Audit: security events record bounded metadata without storing secret or raw payloads.
- Approval: approval is bound to the exact action, actor, input/plan digest, and policy context; it cannot be reused for a changed action.

## Adversarial test cases
- Client attempts to claim low risk, no side effects, or extra permissions.
- Model proposes an unregistered tool or an action outside current grants.
- Tool output contains instruction-like text asking to change goal, reveal secrets, or invoke another tool.
- Retrieved memory contains stale or conflicting instructions.
- External content asks to bypass approval, change policy, or exfiltrate context.
- Owner A tries to query, execute, approve, or retrieve Owner B's records.
- Invalid, oversized, deeply nested, or unexpected tool payloads.
- Secret-like strings in exception messages, output, memory candidates, and audit metadata.
- Tool timeout/ambiguous response with a non-idempotent effect.
- Permission grant expires or is revoked between planning and execution.
- Audit storage unavailable: verify fail-closed behavior for sensitive policy changes and no unsafe retry.

## Acceptance expectations
- Denied actions never call their handler.
- Permission checks use the authenticated actor and registered metadata only.
- Approval-required actions cannot execute without an exact valid approval.
- Prompt-level untrusted labels are accompanied by server-side checks; never rely on model compliance alone.
- Sensitive values are not persisted or returned in error/audit/trace/memory.
- Owner isolation holds in API, database queries, indexes, and UI.
- No automatic retry for ambiguous non-idempotent external operations.
- Security test results are recorded against exact commit and CI run.

## Known limitations to verify
- Tool-output marking does not prevent a model from following adversarial content.
- Comprehensive authorization coverage across every router has not been established by selected-route inspection.
- This checklist is not a substitute for threat modeling, dependency review, or a security-focused test run.
