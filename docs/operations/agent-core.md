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
completed earlier steps are returned with a stable error code; exception
text and internal diagnostics are not exposed. High-risk tools, tools
requiring ungranted permissions, and tools with external side effects remain
blocked until a separate approval workflow is designed and connected.

This endpoint does not invoke the selected model, persist an agent run, or
provide rollback for a tool that has already completed. Only trusted,
server-registered handlers should be added to the registry. The initial
built-in tool remains the deterministic `text.echo` example.


## Persistent run history

Every `POST /agent/execute` response now includes a durable run record.
`GET /agent/runs/{run_id}` retrieves its status, provider/model identifiers,
sanitized plan, tool names, execution count, stable error code, timestamp,
and a SHA-256 digest of non-sensitive request metadata (goal length, tool
names, and requested capabilities), not the raw prompt or tool payloads.

For data minimization, the history table does not store the raw goal, tool
payloads, or tool outputs. The immediate execution response still returns
outputs to the authenticated caller; the history endpoint deliberately does
not. The current implementation records completed, blocked, or failed
synchronous executions. It is not yet a resumable background workflow.


## Workflow step transition integrity

Workflow step updates use a SQLite immediate write transaction and an explicit
transition table. A step can move from pending to running, then to exactly
one terminal state (succeeded, failed, or blocked). Terminal steps cannot be
reopened or replayed through the repository API. This serializes competing
writers and prevents duplicate state transitions.

This is a concurrency and audit-integrity safeguard, not automatic crash
recovery. A process that stops while a step is running leaves that step
ambiguous; it must not be replayed until the system can prove the operation
is idempotent or obtain a safe, explicit recovery decision.


## Runtime budget

Model-driven runs accept a total wall-clock budget from 1 to 30 seconds (default 30).
The orchestrator checks the deadline before each turn, immediately after model inference,
and after each tool returns. A response that arrives after the deadline is discarded before
any proposed tool call can be dispatched. A tool that itself runs past the deadline cannot
be forcibly interrupted by the current synchronous tool contract; its completed result is
recorded and no further turn is started. Provider adapters retain their own finite request
timeouts. Each individual provider request is also capped at 32,000 input characters; if the
serialized prompt (including the tool catalog and observations) exceeds that limit, the run
returns a sanitized `provider_input_budget_exceeded` result before provider dispatch. This
is a cooperative run budget, not a hard process-level execution limit.


## Model-driven tool policy outcomes

The synchronous `POST /agent/run` orchestration loop preserves the policy
engine's decision at the tool boundary. A high-risk or externally side-effecting
proposal that lacks explicit approval returns `approval_required` with the
stable `approval_required` error code. A prohibited-risk or otherwise denied
proposal returns `tool_denied` with `tool_policy_denied`. Neither outcome
increments the successful tool-call count or invokes the registered handler.
Schema/handler failures remain separate sanitized `tool_denied` outcomes.
This is outcome reporting only: the model cannot self-approve, and this endpoint
does not yet provide an approval-granting or resume workflow.


## Specialist registry and bounded delegation

The initial model-driven Agent API exposes a server-defined specialist catalog. A model may
propose one of the registered specialist profiles, but it cannot create or modify profiles.
The initial profiles include `aria_architect`, which analyzes supplied project evidence and
returns bounded architecture/delivery recommendations without tools, plus evidence synthesis
and a narrowly scoped text helper. Each child receives the parent's remaining runtime and
tool-call budgets plus a reserved share of the remaining input-character budget; reserved
shares prevent multiple children from exceeding the root input cap. Delegation is limited to
two children per root run and one level deep; children cannot delegate again. Tool scopes are
built from the parent's registry while preserving the same server-side policy engine.
Child answers are returned to the parent as explicitly untrusted observations, never as
policy or authorization. This is an initial extensible registry, not a dynamic agent
marketplace or a claim of unrestricted autonomous operation.


## Durable model-run parity

Queued `POST /agent/model-runs` requests preserve the requested runtime budget in
their encrypted, owner-bound payload. The worker applies that exact budget when it
constructs the model loop and initializes the same server-defined specialist
registry used by the synchronous `POST /agent/run` endpoint. Specialist tool
allow-lists and the shared policy engine therefore apply consistently in both
execution paths. A durable run still executes under its worker lease and its
result is encrypted before it is made available to the owner.


## Retrieval-quality evaluation

The local reference benchmark is implemented in
`mrhub.knowledge.evaluation.run_reference_evaluation`. Run it with
`python -m mrhub.knowledge.evaluation` from the backend environment. It creates
a temporary SQLite database and a synthetic five-document corpus, then reports
document-level Precision@K, Recall@K, Mean Reciprocal Rank, and hit rate.
It does not read owner data, include retrieved source text in the report, or
access the network. This synthetic benchmark is a regression baseline, not
a claim about retrieval quality on arbitrary production corpora. The API-level
seven-case fixture in `tests/knowledge_eval.json` separately checks rank-one
source selection and citation references.


## Freshness-review expiry

An `owner_reviewed_current` label is an owner attestation, not automatic source
verification. The Agent treats that attestation as current for at most 30 days.
Under `owner_reviewed_current_only`, expired reviews, unknown labels, malformed
or missing review timestamps, and timestamps more than five minutes in the
future are excluded from model context. Explicitly stale sources are counted
separately. Under `include_all`, the evidence remains available but carries
a `freshness_review_expired` marker and the 30-day review-age limit. No URL is
fetched and no claim of independent source verification is made.


## Local knowledge integrity

Before a knowledge chunk is returned to an Agent, retrieval recomputes the
chunk and full-document SHA-256 digests, checks that the source and document
hashes agree, and verifies that the stored chunk offsets still select the
same content from the document. Inconsistent records are excluded from search
results. This protects the local retrieval boundary against accidental or
unauthorized row-level content changes; it does not authenticate the original
publisher or prove that an external source is still current.



## ARIA architecture specialist

The server-defined `aria_architect` profile provides bounded project and
architecture analysis from the goal and evidence supplied by its parent Agent.
It prioritizes reuse of the existing architecture, evidence/assumption
separation, security, maintainability, testability, and measurable acceptance
criteria. It has no tool grants and a three-turn maximum. It cannot inspect a
repository independently, execute tests, deploy changes, approve actions, or
claim external work that was not performed. Its output remains an untrusted
specialist observation and does not grant permissions.
