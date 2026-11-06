# ADR-0002: Isolated Cloudflare Workers Integration Gateway

- **Status:** Proposed
- **Date:** 2026-11-06
- **Owners:** Project owner and maintainers
- **Related work:** Cloudflare gateway stage 1; Hub integration adapter

## Context

The Hub needs a controlled way to inspect Cloudflare resources without placing the Cloudflare provider token in the Hub process, model context, local database, or browser. The gateway must run on Cloudflare Workers and remain separate from the existing Worker named gahop and the gshop11.ir application route.

## Decision

Use a dedicated Cloudflare Worker as the only component holding the Cloudflare API token. The Hub authenticates to the gateway with a separate high-entropy service credential. The gateway exposes typed, read-only operations and never exposes an arbitrary Cloudflare API proxy.

### Trust boundaries

1. CF_API_TOKEN is a Cloudflare Worker secret with least-privilege read-only scopes.
2. GATEWAY_AUTH_TOKEN is a separate Worker secret shared only with the Hub's server-side secret configuration.
3. CF_ACCOUNT_ID and CF_ZONE_ID are fixed Worker variables. Callers cannot choose account or zone identifiers.
4. The Hub never receives the Cloudflare provider token.
5. The gateway returns only projected metadata. Worker secret and plain-text binding values are never returned.
6. No provider response bodies, authorization headers, or secret values are written to logs.
7. All provider requests use fixed endpoint templates, GET only, bounded timeouts, bounded responses, and endpoint-specific pagination.

### Initial capability set

- Authenticated health/readiness.
- Worker script inventory.
- Worker route inventory for the configured zone.
- D1 database metadata inventory.
- Sanitized Worker settings metadata.

D1 SQL and row access, Worker source retrieval, arbitrary API calls, deployments, route changes, secret management, resource deletion, and billing-affecting actions are excluded.

### Authentication and exposure

- The gateway uses a high-entropy bearer credential at the application layer.
- Production must additionally be protected by a Cloudflare Access application with a Service Auth policy and a dedicated service token.
- Staging and production use separate Worker names, secrets, and configuration.
- The first deployment uses an isolated workers.dev hostname. It does not attach a custom domain or route.

### Existing infrastructure isolation

- Do not modify or repurpose the existing gahop Worker.
- Do not change the existing gshop11.ir/api/* route.
- Do not bind the new gateway to the existing gshop-db D1 database.
- The gateway's initial inventory operations are read-only and do not query D1 rows.

## Rollout gates

1. Merge the source and contract tests after CI succeeds.
2. Provision a dedicated least-privilege Cloudflare API token and gateway service token as Worker secrets.
3. Deploy to an isolated staging Worker only after explicit owner approval.
4. Verify authentication failures, route allowlisting, metadata redaction, timeout/size bounds, and provider failures.
5. Configure Cloudflare Access Service Auth for production.
6. Obtain separate owner approval for production deployment and any custom-domain routing.
7. Any future write capability requires a separate ADR, immutable plan fingerprint, explicit approval, pre-execution policy revalidation, rollback artifact, and post-deployment verification.

## Consequences

The Hub receives a stable and narrow Cloudflare integration boundary. Provider credentials stay in Cloudflare, the existing GSHOP Worker and route remain isolated, and the first release cannot mutate Cloudflare resources.
