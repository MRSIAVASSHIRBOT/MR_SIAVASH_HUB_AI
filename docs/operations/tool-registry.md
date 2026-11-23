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


## Per-invocation lifecycle observation

The registry supports an optional metadata-only lifecycle observer. Events carry
the registered tool name, transition stage, keyed input/output fingerprints,
and a bounded reason code; they never include raw payloads, result bodies,
exception messages, or credentials. Fingerprints use HMAC-SHA-256 with an
ephemeral process-local key: equal values can be correlated only within the
same process lifetime. They intentionally do not correlate across restarts,
are not authorization evidence, and must not be treated as anonymized data.

The ordered lifecycle distinguishes input validation, authorization decisions,
handler start/return/failure, output validation, success, and unknown outcomes.
Replay safety is determined by the server-owned `ToolDefinition.replay_safety`
classification—not by `external_side_effect` or a model-provided label. An
interrupted failure or invalid output from a `reconcile_required` tool is
reported as `unknown_outcome`; explicitly `retry_safe` tools are reported as
ordinary handler/output failures.

Observer callback failures are sanitized to a warning and do not alter policy,
handler invocation, output validation, or the final tool result. The
`AgentCore.execute` method exposes the hook as `on_tool_lifecycle` so a caller
can correlate events with durable workflow step/attempt identifiers.

## Policy evaluation API

The authenticated `POST /policy/evaluate` endpoint accepts only a registered action name. It resolves the matching `ToolDefinition` on the server and derives risk class, required permissions, and external-side-effect status from that trusted definition. Active permission grants are loaded from the authenticated owner's persisted grant records. Caller-supplied permission, risk, side-effect, or approval claims are rejected.

The response is inspection-only. It explicitly includes `evaluation_only=true`, `execution_authorized=false`, and `action_executed=false`. A caller must still use the separate authenticated tool invocation endpoint, which rebuilds the registered definition and checks current grants before any handler is invoked.

High-impact and external-side-effect tools require a separate owner confirmation through an action-bound approval receipt. The flow is:

1. `POST /tools/{tool_name}/approvals` validates the input schema, confirms the authenticated owner's current permission grants, and creates a short-lived pending request. It stores only a canonical payload digest, a fingerprint of the tool contract/handler, owner identity, and lifecycle timestamps; the payload itself is never persisted.
2. `POST /tools/{tool_name}/approvals/{approval_id}/decision` records an explicit `approved` or `rejected` decision from that same authenticated owner. A changed/expired tool definition invalidates the pending approval.
3. `POST /tools/{tool_name}/invoke` accepts the `approval_id` alongside the payload. The server revalidates current grants, recomputes the canonical payload digest and tool fingerprint, and atomically consumes the approved receipt immediately before handler invocation.

Receipts are owner-scoped, action-bound, expiring (60–900 seconds), and single-use. They cannot be replayed for another payload, tool, owner, or changed handler definition. The handler fingerprint includes the code object, declared schemas, policy metadata, default arguments, and a bounded deterministic projection of closure-bound primitive configuration (including path values). Arbitrary captured objects are not introspected; only their concrete type is represented, avoiding accidental serialization of clients or credentials. Trusted server-owned clients may explicitly expose a bounded `approval_fingerprint()` containing only non-secret configuration identity; the Cloudflare gateway client binds its normalized endpoint, a one-way digest of its gateway credential, timeout, and response-size limit. Per-request correlation IDs are intentionally excluded. A tool whose security-relevant configuration lives in a mutable opaque object must expose that configuration through an explicit immutable server-owned definition field before relying on it for approval binding. Permission grants remain independently required; an approval receipt never creates or extends a permission grant. The server never accepts a client-supplied `user_approved` boolean. Because a receipt is consumed before calling the handler, a handler failure or ambiguous external outcome does not make the receipt replayable; the owner must review the outcome before requesting a new approval. Task-level approvals remain a separate mechanism and are not interchangeable with tool-invocation receipts.

The same owner-bound receipt can be attached to the matching tool step in a durable `POST /agent/workflows` request using its `approval_id`. The authenticated planning path performs a non-consuming validation against the current owner grants, canonical tool input, and current tool-definition fingerprint. The worker independently rebuilds the registry and repeats that validation after decrypting the owner-scoped workflow request. Immediately before invoking the handler, it atomically consumes the receipt again. A revoked permission, changed tool implementation, changed payload, expired/rejected/consumed receipt, or missing receipt keeps the workflow fail-closed. The approval ID is part of the durable request/step digest so it cannot be silently substituted during resume. Migration V57 creates the owner-scoped approval receipt store.
