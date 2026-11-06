# Cloudflare Integration Gateway — Stage 1

This directory contains the isolated Cloudflare Worker gateway source for the Hub's read-only Cloudflare integration.

## Scope

The gateway is intentionally read-only. It exposes a fixed set of typed operations:

| Method | Path | Capability |
|---|---|---|
| GET | /health | Authenticated health/readiness |
| GET | /v1/workers | List Worker metadata |
| GET | /v1/worker-routes | List Worker route metadata |
| GET | /v1/d1-databases | List D1 database metadata |
| GET | /v1/workers/{script}/settings | Read safe Worker settings metadata |

The Worker does not accept arbitrary Cloudflare URLs, HTTP methods, headers, request bodies, account IDs, zone IDs, or D1 SQL. Account and zone scope come only from server-side configuration. Worker binding values (including secret and plain-text values) are never returned.

## Required configuration

Non-secret Worker variables:

- \`CF_ACCOUNT_ID\`: one explicitly approved Cloudflare account ID.
- \`CF_ZONE_ID\`: one explicitly approved zone ID.

Worker secrets:

- \`CF_API_TOKEN\`: a least-privilege Cloudflare API token with only the read permissions needed for the enabled operations:
  - Workers Scripts Read
  - Workers Routes Read
  - D1 Read
- \`GATEWAY_AUTH_TOKEN\`: a separate high-entropy service credential used by the Hub to authenticate to this gateway. Keep the matching value in the Hub's secret environment as \`MRH_CLOUDFLARE_GATEWAY_TOKEN\`; never commit either value.

Do not reuse the token used by the ChatGPT Cloudflare connector. The connector credential is not exposed to this Worker source or to the Hub.

## Security controls

- Fixed Cloudflare API origin and endpoint templates.
- Exact GET-only route allowlist; query strings and request bodies are rejected.
- Constant-time comparison of fixed-length SHA-256 token digests.
- Account and zone identifiers are taken from Worker variables, never caller input.
- Eight-second provider timeout, 1 MiB response cap, bounded pagination and item limits.
- Redirects, non-JSON responses, malformed envelopes, and provider failures fail closed.
- Sanitized error codes; no upstream response body or credential is returned.
- Structured request logs contain only request ID, operation name, status, and duration.
- Responses use \`Cache-Control: no-store\`.

## Deployment boundary

This source is not deployed by this change. Stage 1 must first be deployed to an isolated staging Worker on a dedicated \`workers.dev\` hostname. Do not attach it to \`gshop11.ir\`, reuse the existing \`gahop\` Worker, or alter any existing routes.

Before deployment, provision the two Worker secrets and the two non-secret variables in a staging environment, then perform authenticated read-only acceptance tests. Production deployment, custom-domain routing, D1 row access, resource writes, secret rotation, and destructive operations require separate approval and a reviewed change plan.

Cloudflare Access Service Auth must protect the gateway before production. Use a dedicated service token and a Service Auth policy for the gateway hostname. The gateway's own bearer credential remains required as defense in depth.

## Local tests

From the repository root:

\`\`\`sh
node --check cloudflare/gateway/src/index.js
node --test cloudflare/gateway/test/*.test.mjs
\`\`\`

The tests mock the Cloudflare API and never use production credentials or modify Cloudflare resources.
