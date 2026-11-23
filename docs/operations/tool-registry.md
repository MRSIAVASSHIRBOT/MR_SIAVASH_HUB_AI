# Tool registry operations

The tool layer uses explicit registration and typed input/output contracts.
The authenticated `GET /tools` endpoint lists only registered tools and
publishes their JSON schemas, risk class, required permissions, and external
side-effect declaration.

## Invocation

`POST /tools/{tool_name}/invoke` accepts a JSON object under `payload`.
Unknown tools return 404 and invalid input returns a sanitized 422 response.
Tool invocation requests do not accept client-supplied permission grants or approval flags. Only the dedicated owner-authenticated grant endpoints can persist allow-listed grants; invocation derives active permissions from the authenticated owner's server-side records.

The initial built-in `text.echo` tool is deterministic and has no external
side effects. It exists to exercise the registry contract; it is not an AI
model or an external integration.

## Policy boundaries

- Tool names must be explicitly registered; unknown names fail closed.
- Inputs and outputs are validated against registered Pydantic models.
- Required permissions are evaluated by the server-side policy engine.
- External side effects and high-risk operations require explicit approval.
- Tool handlers are never exposed in the catalog or API response.
- No shell, arbitrary Python, network access, or dynamic tool loading is
  provided by the initial registry.


## Owner-scoped permission grants

The authenticated owner can manage a small, explicit allow-list of tool permissions:

- GET /tools/grants lists only the current owner's active grants.
- PUT /tools/grants/cloudflare.read creates or renews a read-only Cloudflare metadata grant.
- DELETE /tools/grants/cloudflare.read revokes that grant.

Grants expire automatically. The default lifetime is one hour; callers may request 60 seconds through 24 hours. Unsupported permissions are rejected. Grant and revoke mutations write their audit events in the same SQLite transaction as the permission change.

Tool invocation loads active permissions from the authenticated session owner in the server-side database. The request body cannot supply permissions or approval flags. Every invocation outcome records only allow-listed metadata and a generated correlation ID; input payloads, provider responses, and credentials are not recorded.


## Optional Cloudflare read-only tools

When the isolated gateway is fully configured, the authenticated tool catalog registers four fixed operations:

- `cloudflare.workers.list`
- `cloudflare.worker_routes.list`
- `cloudflare.d1_databases.list` (metadata only; no row access)
- `cloudflare.worker.settings.read` (binding names/types only; no values)

Every operation requires the owner's active `cloudflare.read` grant. The grant is never inferred from model output or the invocation payload. It defaults to one hour and can be bounded from 60 seconds to 24 hours. Revocation or expiry causes subsequent invocations to be denied. Gateway credentials remain in server-side settings and never enter tool schemas, results, audit metadata, or frontend assets.

The integration remains disabled by default. Enabling it requires a dedicated HTTPS `*.workers.dev` gateway URL and a separate gateway token; the Cloudflare provider token must remain exclusively in the gateway Worker. Only fixed GET operations are exposed. No deployments, route mutations, secrets, D1 rows, source downloads, deletions, or billing operations are registered.


## Policy evaluation API

The authenticated `POST /policy/evaluate` endpoint accepts only a registered
action name. It resolves the matching `ToolDefinition` on the server and
derives risk class, required permissions, and external-side-effect status from
that trusted definition. Active permission grants are loaded from the
authenticated owner's persisted grant records. Caller-supplied permission,
risk, side-effect, or approval claims are rejected.

The response may report a policy decision such as `allow`, but the endpoint is
inspection-only. Every response explicitly includes
`evaluation_only=true`, `execution_authorized=false`, and
`action_executed=false`. A caller must still use the separate authenticated
tool invocation endpoint, which rebuilds the registered definition and checks
current grants before any handler is invoked.

The current direct tool-invocation API does not yet accept a server-issued,
action-bound approval receipt. Therefore, a tool whose policy requires explicit
approval remains fail-closed at this endpoint and returns
`require_approval`; it is not executable through a caller-supplied
`user_approved` flag (unknown request fields are rejected). Task-level
approval records are not substitutes for tool-invocation approvals because
they do not bind the exact tool definition and canonical payload digest.
A future approval flow must issue an owner-scoped, expiring, one-time approval
bound to that exact action before enabling such invocations.
