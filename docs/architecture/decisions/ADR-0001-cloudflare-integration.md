# ADR-0001: Hub-Side Cloudflare Gateway Client

- **Status:** Implemented in source behind explicit configuration and owner grant; isolated staging acceptance and deployment remain pending.
- **Date:** 2026-11-06
- **Owners:** Project owner and maintainers
- **Related work:** GitHub issue #299; PR #300; ADR-0002

## Context

MR_SIAVASH_HUB_AI is a local-first modular monolith. Its canonical Tool Registry, policy engine, audit service, and bounded worker runtime remain the authority for tool execution. Cloudflare access is provided by the isolated Workers gateway described in ADR-0002.

The Hub must not hold a Cloudflare provider API token, call \`api.cloudflare.com\` directly, or expose an arbitrary network proxy to agents.

## Decision

The Hub uses a typed, optional, synchronous client for the isolated Cloudflare Workers gateway. The client is compatible with the existing synchronous ToolRegistry handler contract and exposes only fixed read-only operations. Four agent-callable tools are registered only when gateway configuration is valid; each requires the owner's active server-side `cloudflare.read` grant.

### Trust boundaries

1. The Cloudflare provider token exists only as a secret binding in the dedicated Cloudflare gateway Worker.
2. The Hub stores only the separate gateway bearer credential as \`MRH_CLOUDFLARE_GATEWAY_TOKEN\`.
3. The gateway URL is deployment configuration and must be HTTPS, a public DNS hostname, and contain no path, query, fragment, or userinfo.
4. The client uses fixed GET routes, bounded timeouts and response bytes, rejects redirects, and disables environment proxy inheritance.
5. The client validates response envelopes and typed output schemas; errors never include response bodies or credentials.
6. Worker settings expose binding names and types only. Binding values are never accepted in Hub output models.
7. The integration is disabled by default and remains unavailable when required configuration is absent.
8. Tool registration uses the existing ToolRegistry and PolicyEngine. Each Cloudflare tool requires the owner-scoped `cloudflare.read` grant; invocation outcomes are audited using allow-listed metadata and correlation IDs.

### Initial read-only capability set

- List Worker metadata.
- List Worker route metadata.
- List D1 database metadata.
- Read projected Worker settings metadata.

D1 row access, Worker source retrieval, arbitrary API calls, deployments, route changes, secret management, resource deletion, and billing-affecting operations are excluded.

## Alternatives considered

### Direct Cloudflare API calls from the Hub

Rejected. This would place the provider token in the Hub process and duplicate the credential boundary that ADR-0002 intentionally isolates.

### Agent-generated arbitrary HTTP requests

Rejected. Only typed, fixed endpoint methods are allowed.

### Parallel authorization or audit implementation

Rejected. The existing ToolRegistry, PolicyEngine, owner grant lifecycle, and AuditLogger remain the single policy and audit authority. This PR does not create a second system.

## Implementation constraints

- Preserve local-only operation when gateway configuration is absent.
- Use the existing \`Settings\` and \`SecretStr\` conventions.
- Never place credentials in SQLite, source control, frontend assets, prompts, tool results, or logs.
- No implicit retries or fallback to direct Cloudflare API access.
- No production Cloudflare resources are changed by this source-only integration.

## Rollout gates

1. Accept ADR-0002's gateway trust boundary.
2. Complete gateway client contract tests and exact-head CI.
3. Complete exact-head tests for the owner-grant-gated ToolRegistry integration.
4. Perform authenticated read-only acceptance against an isolated staging Worker.
5. Obtain separate approval for any production deployment or future write capability.

## Consequences

The Hub has a narrow typed client and four permission-gated read-only tools while Cloudflare provider credentials remain isolated in the gateway. The integration remains disabled by default. Source changes do not deploy or modify Cloudflare resources.
