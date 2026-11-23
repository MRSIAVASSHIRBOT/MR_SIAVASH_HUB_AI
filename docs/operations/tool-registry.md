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

The authenticated `POST /policy/evaluate` endpoint accepts only a registered action name. It resolves the matching `ToolDefinition` on the server and derives risk class, required permissions, and external-side-effect status from that trusted definition. Active permission grants are loaded from the authenticated owner's persisted grant records. Caller-supplied permission, risk, side-effect, or approval claims are rejected.

The response is inspection-only. It explicitly includes `evaluation_only=true`, `execution_authorized=false`, and `action_executed=false`. A caller must still use the separate authenticated tool invocation endpoint, which rebuilds the registered definition and checks current grants before any handler is invoked.

The current direct tool-invocation API does not accept a server-issued, action-bound approval receipt. Therefore, high-impact and external-effect tools remain fail-closed with `require_approval`; a caller-supplied approval flag is not accepted. Task-level approvals are not substitutes for tool-invocation approvals because they are not bound to the exact tool definition and canonical payload digest. A future approval flow must issue an owner-scoped, expiring, one-time receipt bound to that exact action before enabling those invocations.

## Registration-time contract validation

A tool is accepted into the registry only after all definition fields pass
server-side validation:

- Tool names and descriptions are bounded and canonical.
- Input and output schemas must be actual Pydantic `BaseModel` subclasses.
- The handler must be callable and synchronous; coroutine/async-generator functions
  and awaitable/async-generator handler results are rejected because the current
  invocation boundary is synchronous.
- Risk classification must be a `RiskClass` value, not a client/model string.
- The external-side-effect flag must be an actual boolean.
- Required permissions must be an immutable `frozenset` of at most 32 bounded,
  canonical permission identifiers.

The registry inserts a definition only after every check succeeds. Invalid
definitions are rejected at startup/registration rather than failing later
during tool invocation.

## Execution isolation limitation

Registration validation does not provide process isolation or a hard runtime
timeout for arbitrary Python handlers. The current registry invokes trusted,
server-registered synchronous handlers in-process. Do not add untrusted or
long-running handlers and do not simulate a hard timeout with a background
thread: a thread timeout cannot safely terminate a side-effecting operation.
Hard execution deadlines require a separately designed process/container
boundary with cancellation and idempotency semantics.


## Explicit replay-safety classification

Policy risk and replay safety are different ToolDefinition properties:

- `external_side_effect` describes whether an operation affects an external
  system and therefore requires the relevant approval policy.
- `replay_safety` describes whether the same handler can be invoked again after
  a crash with an ambiguous in-flight outcome.

The default is `reconcile_required`. A handler is classified
`retry_safe` only through an explicit server-owned ToolDefinition declaration.
An interrupted step with this declaration is persisted as `safe_tool` and may
enter `retry_wait`. Other interrupted steps are persisted as
`unknown_outcome` and require reconciliation, including local state-mutating
handlers whose `external_side_effect` flag is false.

Read-only device-registry and Cloudflare metadata operations, plus the pure
`text.echo` handler, are explicitly marked retry-safe. The app-launch
submission and every other mutating or unclassified handler remain
reconciliation-required by default. Model output and API request payloads
cannot set or override this field.

This metadata is persisted into the durable step kind when a workflow is
created. It does not change the meaning of an existing in-flight workflow.
Legacy workflow rows are not rewritten automatically: a pre-existing
`safe_tool` step retains its original persisted classification. If the current
server-generated definition no longer matches the persisted step metadata,
resume validation fails closed rather than silently reclassifying or replaying
the old step. Operators must reconcile such a workflow before continuing.

## Per-invocation lifecycle observation

The registry supports an optional metadata-only lifecycle observer. Events carry
the registered tool name, transition stage, canonical input/output digests,
and a bounded reason code; they never include raw payloads, result bodies,
exception messages, or credentials.

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

The current direct tool-invocation API does not accept a server-issued, action-bound approval receipt. Therefore, high-impact and external-effect tools remain fail-closed with `require_approval`; a caller-supplied approval flag is not accepted. Task-level approvals are not substitutes for tool-invocation approvals because they are not bound to the exact tool definition and canonical payload digest. A future approval flow must issue an owner-scoped, expiring, one-time receipt bound to that exact action before enabling those invocations.
