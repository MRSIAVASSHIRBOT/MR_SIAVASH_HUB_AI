# Agent core operations

The authenticated `POST /agent/plan` endpoint connects the model router,
registered tool catalog, and server-side policy engine into one planning
response. A request supplies a goal, required model capabilities, local
preference, and up to five explicitly named tools with typed payloads.

## Planning behavior

1. The model router selects a registered model matching the requested
   capabilities.
2. Each requested tool is looked up in the allow-listed tool registry.
3. Tool input is validated against its registered Pydantic schema.
4. The policy engine classifies each tool step as ready, approval-required,
   blocked, invalid-input, or not-registered.
5. The API returns an ordered plan and an execution-readiness flag.

## Current execution boundary

This is the initial deterministic planning core, not an autonomous LLM agent.
It does not send the goal to a model, run inference, execute tools, download
models, or create external side effects. `decision_mode` is always
`plan_only`; `model_inference_started` and `tools_executed` are always
false. The endpoint is designed to establish orchestration contracts before
adding separately approved execution and persistent multi-step workflows.


## Controlled tool execution

The authenticated `POST /agent/execute` endpoint is the first execution
capability. It accepts the same bounded request as `/agent/plan`, rebuilds
the plan on the server, and starts no tool unless every requested step is
registered, schema-valid, and allowed by the policy engine.

Execution is sequential and stops at the first handler failure. Results from
completed earlier steps are returned with a stable error code; exception text
and internal diagnostics are not exposed. High-risk tools, tools requiring
ungranted permissions, and tools with external side effects remain blocked
until a separate approval workflow is designed and connected.

This endpoint does not invoke the selected model, persist an agent run, or
provide rollback for a tool that has already completed. Only trusted,
server-registered handlers should be added to the registry. The initial
built-in tool remains the deterministic `text.echo` example.


## Persistent run history

Every `POST /agent/execute` response now includes a durable run record.
`GET /agent/runs/{run_id}` retrieves its status, provider/model identifiers,
sanitized plan, tool names, execution count, stable error code, timestamp, and
a SHA-256 digest of non-sensitive request metadata (goal length, tool names,
and requested capabilities), not the raw prompt or tool payloads.

For data minimization, the history table does not store the raw goal, tool
payloads, or tool outputs. The immediate execution response still returns
outputs to the authenticated caller; the history endpoint deliberately does
not. The current implementation records completed, blocked, or failed
synchronous executions. It is not yet a resumable background workflow.


## Workflow step transition integrity

Workflow step updates use a SQLite immediate write transaction and an explicit
transition table. A step can move from pending to running, then to exactly one
terminal state (succeeded, failed, or blocked). Terminal steps cannot be
reopened or replayed through the repository API. This serializes competing
writers and prevents duplicate state transitions.

This is a concurrency and audit-integrity safeguard, not automatic crash
recovery. A process that stops while a step is running leaves that step
ambiguous; it must not be replayed until the system can prove the operation is
idempotent or obtain a safe, explicit recovery decision.
