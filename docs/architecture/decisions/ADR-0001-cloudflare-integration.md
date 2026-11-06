# ADR-0001: Policy-Governed Cloudflare Integration

- **Status:** Proposed
- **Date:** 2026-11-06
- **Owners:** Project owner and maintainers
- **Related work:** GitHub issue #299

## Context

MR_SIAVASH_HUB_AI is a local-first modular monolith. Its canonical Tool Registry, policy engine, audit service, and bounded worker runtime are the authority for tool execution. Cloudflare currently operates separately from the Hub; repository inspection did not identify an existing Cloudflare adapter.

The project needs a controlled integration path for inventory, diagnostics, and eventually approved deployment operations without creating a second authorization system or exposing Cloudflare credentials to model context.

## Decision proposal

Implement Cloudflare integration as an optional outbound adapter behind the existing integration ports and Tool Registry.

The first implementation is **read-only**. It may inventory explicitly allowlisted account resources and return sanitized metadata. It must not expose a generic arbitrary-API-request tool.

### Trust boundaries

1. The Cloudflare API token remains in the local deployment secret manager or process environment. It is never stored in SQLite, source control, frontend assets, prompts, tool results, or logs.
2. The adapter accepts typed operation inputs, not arbitrary URL, HTTP method, headers, or request bodies supplied by an agent.
3. Account identifiers and resource identifiers are validated against configured allowlists.
4. Binding inventory returns binding names and types only. Secret values and plaintext binding values are never returned.
5. Every invocation is scoped to the authenticated owner/workspace, passes policy evaluation, uses bounded timeouts and pagination, and emits a redacted audit event.
6. Errors use stable codes and sanitized messages. Raw response bodies and authorization headers are not logged.

### Initial read-only capability set

- List configured Workers and retrieve sanitized deployment metadata.
- List Worker routes and domains.
- List D1 database metadata and schema names where explicitly permitted.
- Inspect Worker binding names/types without returning values.
- Report compatibility date, observability flags, and deployed version identifiers.

D1 row reads are excluded from the initial capability set. They require a separately reviewed data-access contract and explicit scope.

### Write capability gate

Worker deployments, route changes, D1 mutations, secret updates, resource deletion, and billing-affecting operations are out of scope for the first release.

A later write-capable stage must provide:
- An immutable, human-readable change plan and diff.
- Explicit owner approval bound to the exact plan fingerprint.
- Revalidation of policy and approval immediately before execution.
- A non-production target and rollback artifact.
- Post-deployment verification tied to the exact deployed version.

## Alternatives considered

### Direct Cloudflare API calls from agent-generated code

Rejected. This bypasses typed tool contracts, creates an arbitrary network capability, and makes authorization, redaction, and auditing difficult to enforce.

### A separate Cloudflare orchestration service

Deferred. It would duplicate policy, jobs, audit, and lifecycle infrastructure before measured scale or isolation requirements justify a service boundary.

### Wrangler subprocess execution from the Hub

Deferred. It introduces process-execution and local-environment risks. A typed API adapter is the preferred initial path. Wrangler may remain a maintainer-operated development workflow outside agent invocation.

## Implementation constraints

- Preserve local-only operation when Cloudflare credentials are absent.
- Use the repository's existing configuration and dependency conventions.
- Keep Cloudflare SDK/API details inside the adapter.
- Do not add arbitrary shell execution or arbitrary HTTP access to the Tool Registry.
- Use least-privilege Cloudflare tokens; read-only tokens for the initial phase.
- Add tests for authorization, account/resource scoping, redaction, timeouts, pagination, malformed responses, and provider failures.
- Never use production secrets in tests or fixtures.

## Rollout plan

1. Review and accept this ADR.
2. Implement typed read-only contracts and adapter.
3. Register read-only tools with explicit grants and audit metadata.
4. Add mocked contract tests and CI checks.
5. Perform a live read-only acceptance test against an explicitly selected account.
6. Evaluate write operations in a separate ADR and approval-gated milestone.

## Consequences

The Hub gains a safe path to discover and observe Cloudflare resources while retaining a single policy authority. The first milestone intentionally does not deploy code, mutate D1, change routes, or manage secrets.

## Review triggers

Revisit this decision if Cloudflare operations require a separate deployment boundary, multiple organizations/accounts need isolation, or measured API volume justifies a dedicated service.
