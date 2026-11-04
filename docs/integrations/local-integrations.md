# Local Integration Contract

**Status:** Health-only adapters are implemented on `main` and disabled by default. Neither adapter installs software, launches processes, executes code, invokes remote tools, routes prompts, or publishes messages.

## Canonical internal names

| Integration | Internal ID | Authenticated status API | Environment prefix |
|---|---|---|---|
| Local assistant runtime | `assistant_gateway` | `GET /integrations/assistant-gateway/status` | `MRH_ASSISTANT_GATEWAY_*` |
| Local coding service | `code_engine` | `GET /integrations/code-engine/status` | `MRH_CODE_ENGINE_*` |

These are HUB-owned, vendor-neutral integration IDs. They do not rename or claim ownership of external products. The two adapters remain separate because their responsibilities differ, while sharing one validation and health-probe implementation.

## Protocol versioning

The local integration protocol is versioned independently from the capability-discovery schema. Current `contract_version` is `1.0` and appears in every integration status response, including disabled and invalid-configuration results. `integration_contract_version` in `/agent/capabilities` identifies the same contract. A breaking change to status fields, status meanings, or request semantics requires a new major version; additive optional fields may remain within the current major version.

## Provider adapter lifecycle contract

Model adapters are registered through one injected ProviderRegistry; ModelRouter preserves that exact registry instance and maintains the matching capability descriptor catalog. A failed or duplicate registration must not leave the descriptor catalog and adapter registry partially updated.

Before dispatch, the router calls the selected adapter's bounded health(timeout_seconds=2.0) contract. The result must be a ProviderHealth value with a real boolean available field and a non-empty string reason_code. A malformed health result is a provider contract violation and generation is not started. A well-formed unavailable result fails closed; the router does not silently substitute another provider after selection.

The health check is an adapter lifecycle gate, not proof that inference will succeed. Provider implementations remain responsible for enforcing their own network/request timeouts, classifying transient failures, and avoiding logging prompts, credentials, or response bodies. Agent planning may select from registered descriptors without running inference; actual dispatch is performed only by the explicit router generation path. MCP tool invocation remains separate and continues to use the canonical ToolRegistry and its shared PolicyEngine.

## Shared configuration contract

Each integration uses the same settings shape:

- `ENABLED=false` — disabled by default.
- `BASE_URL` — explicit HTTP(S) URL using a literal loopback IP only.
- `HEALTH_PATH=/health` — absolute path only; traversal and ambiguous encodings are rejected.
- `TIMEOUT_SECONDS=2` — bounded from 0.2 to 10 seconds.
- `MAX_RESPONSE_BYTES=8192` — bounded from 256 to 16,384 bytes.

The complete environment variable names are formed from the integration-specific prefix above, for example `MRH_CODE_ENGINE_BASE_URL`.

## Shared health response

Both status endpoints return the same status vocabulary:

- `disabled`: disabled; no outbound request was made.
- `invalid_configuration`: URL or health path failed validation.
- `reachable`: a successful response was received within the byte limit.
- `unreachable`: request failed or returned a non-success status.
- `rejected_redirect`: redirect was not followed.
- `response_too_large`: response exceeded the configured limit.

Responses never include the external response body or configured URL. Probes disable environment proxy inheritance and redirects, accept literal loopback IPs only, reject encoded or ambiguous path segments, and enforce the configured response-byte limit while streaming.

## Capability discovery

Authenticated `GET /agent/capabilities` provides a versioned, read-only inventory. Its `integrations` object reports each integration's enabled/configured state and status endpoint. Health remains `not_checked` until the corresponding status endpoint is explicitly called. Discovery does not probe networks, run inference, execute tools, download code, or activate capability sources.

## Ownership and security boundaries

- **HUB:** authentication, policy, approvals, audit records, durable jobs, workflow execution, model selection, and recovery.
- **Assistant runtime:** its own sessions, channels, plugins, and runtime state.
- **Code engine:** its own coding workspace and execution environment.
- **Adapters:** configuration validation and bounded, sanitized health checks only.

The services must not share a database or bypass HUB authorization. A future execution bridge requires a separately reviewed typed API contract, explicit permission mapping, approval gates, audit records, idempotency, and safe recovery. No arbitrary shell or code execution is exposed by these adapters.

## Reviewed product mapping: OpenClaw

OpenClaw is a compatible candidate for the HUB-owned `assistant_gateway` slot; it is not a new internal integration ID and its product name is not renamed. The documented local Gateway default is port `18789`. Its unauthenticated `GET /health` (also `/healthz`) is a **liveness-only** check: a successful probe proves that the HTTP listener answered, not that an agent, model provider, or channel is ready. Configure the adapter explicitly with `MRH_ASSISTANT_GATEWAY_ENABLED=true`, `MRH_ASSISTANT_GATEWAY_BASE_URL=http://127.0.0.1:18789`, and `MRH_ASSISTANT_GATEWAY_HEALTH_PATH=/health`; keep it disabled until OpenClaw is installed and configured separately.

Do not put `OPENCLAW_GATEWAY_TOKEN`, `OPENCLAW_GATEWAY_PASSWORD`, or any other Gateway secret into HUB health-probe settings. OpenClaw documents its bearer-authenticated HTTP tool invocation surface as trusted operator access to the Gateway, not as a narrow per-tool identity. Therefore this health-only adapter deliberately sends no OpenClaw credential and does not call `/tools/invoke`, agent/chat endpoints, WebSocket RPC, or admin RPC. A future inference or task bridge requires a separate security design, explicit credential custody, least-privilege authorization, user approval, auditability, bounded execution, and cancellation/reconciliation tests.

OpenClaw compatibility is not claimed as end-to-end integration by this mapping. The current adapter only checks liveness. Deep readiness and actual assistant requests remain separate acceptance gates.

**Upstream references (reviewed 2026-11-03):** [OpenClaw health checks](https://docs.openclaw.ai/gateway/health), [Gateway web interfaces and authentication](https://docs.openclaw.ai/web), [Tools invoke API and its operator-access boundary](https://docs.openclaw.ai/gateway/tools-invoke-http-api).

## Reviewed product mapping: SiaCode

The separate `Siavashc/SiaCode` repository is a **candidate** for the HUB-owned `code_engine` role, not a compatible runtime adapter today. Its README describes a Windows launcher, a local Anthropic-compatible proxy, an ngrok tunnel, and a remote molab kernel; it also documents a remote-kernel API capable of running Python. The reviewed README does not define a stable, authenticated, loopback HTTP health endpoint or a narrow typed coding-request API matching this contract. Consequently, do not point `MRH_CODE_ENGINE_BASE_URL` at an assumed port, invoke its launcher from the HUB, execute its scripts, create tunnels, or download its model automatically.

A future SiaCode adapter can be reconsidered only after the upstream project exposes a documented local health endpoint and a constrained request contract with authentication, explicit workspace scope, bounded inputs/outputs, cancellation, and auditable outcomes. Any remote execution must remain an explicitly approved external operation; it must not bypass the HUB policy engine or workflow recovery rules. The SiaCode repository is MIT-licensed according to its repository metadata, but that does not by itself establish runtime compatibility or operational safety.

**Upstream reference (reviewed 2026-11-03):** [Siavashc/SiaCode README and source](https://github.com/Siavashc/SiaCode).
