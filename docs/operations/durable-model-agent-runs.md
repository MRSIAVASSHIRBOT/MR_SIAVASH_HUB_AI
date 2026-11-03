# Durable model-driven Agent runs

The synchronous `POST /agent/run` endpoint remains available for short, bounded interactive execution. Long-running or queue-managed execution uses the durable workflow path described here.

## Submit a run

`POST /agent/model-runs` accepts the same `AgentRunRequest` body as `POST /agent/run` and requires an `Idempotency-Key` header.

The endpoint validates that the explicitly selected provider is available, assembles the owner-scoped context, encrypts the request envelope, and atomically creates a queued `agent.model_run` task and workflow. It does not call the model.

The request uses the standard authenticated JSON API. A repeated key with the same request returns the original workflow identifier and current idempotency status. Reusing the key with a different request returns HTTP 409.

## Worker execution and recovery

The pull-driven Worker dispatches `agent.model_run` under its existing fenced lease. The encrypted envelope is bound with AES-GCM associated data to the workflow ID, task ID, and owner ID. The same encrypted row is replaced with the encrypted result after execution; the plaintext answer and tool observations are never written to `worker_executions.result_json`.

The model/tool loop is represented as one `model_inference` workflow step. This is deliberately conservative: the loop may contain multiple provider calls and tool invocations, and the current orchestrator does not persist resumable per-turn state. If the worker is interrupted while that step is active, recovery marks it `unknown_outcome` and the workflow `recovery_required`. It is not automatically replayed.

A configured `MRH_WORKFLOW_PAYLOAD_KEY` is mandatory. It must be a URL-safe Base64 encoding of exactly 32 random bytes. There is no plaintext fallback and the application does not generate a production key. Keep the key in deployment secret management and back it up securely; losing it makes encrypted requests and results unreadable.

## Read and cancel

- `GET /agent/model-run-workflows/{workflow_id}` returns metadata only to the owning user. The encrypted result is decrypted only after a successful or cancelled terminal workflow state.
- `POST /agent/model-run-workflows/{workflow_id}/cancel` cancels queued work immediately or requests cooperative cancellation of a running model loop.
- A cancellation request cannot forcibly interrupt a provider call already in progress. The worker observes the request at safe boundaries and records the resulting execution state.

The API never returns ciphertext, encryption keys, prompts from another owner, or internal worker exception text.

## Knowledge freshness policy

Queued model runs use the same `knowledge_freshness_policy` contract as the synchronous Agent endpoint:

- `include_all` remains the default and preserves existing retrieval behavior.
- `owner_reviewed_current_only` includes only knowledge sources with an owner-reviewed-current status and a review timestamp.
- Stale, unknown, and incomplete review records are filtered before evidence is encrypted and queued.
- The encrypted workflow result retains the policy and bounded excluded-source counts in `context_summary`; prompts and evidence remain encrypted.
- Owner review is a manual assertion, not automatic verification. Retrieved content remains untrusted and cannot grant tool permissions.

The durable submission response includes the policy and exclusion counts, while the workflow result preserves the same summary after worker execution.

## Operator UI

The authenticated operator panel offers a separate queued-execution action beside the synchronous Agent run. It creates an `Idempotency-Key` with the browser cryptographic API, displays the returned workflow ID, and provides explicit manual status refresh and cooperative cancellation. No automatic polling is performed. The workflow ID can be pasted back into the panel after a page reload; result data is retrieved from the owner-scoped API only.
