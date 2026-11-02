# Local Integration Contract

**Status:** Initial health-only adapters on a feature branch. Both integrations are disabled by default. Neither adapter installs software, launches processes, executes code, invokes remote tools, routes prompts, or publishes messages.

## Canonical internal names

| Integration | Internal ID | Authenticated status API | Environment prefix |
|---|---|---|---|
| Local assistant runtime | `assistant_gateway` | `GET /integrations/assistant-gateway/status` | `MRH_ASSISTANT_GATEWAY_*` |
| Local coding service | `code_engine` | `GET /integrations/code-engine/status` | `MRH_CODE_ENGINE_*` |

These are HUB-owned, vendor-neutral integration IDs. They do not rename or claim ownership of external products. The two adapters remain separate because their responsibilities differ, while sharing one validation and health-probe implementation.

## Protocol versioning

The local integration protocol is versioned independently from the capability-discovery schema. Current `contract_version` is `1.0` and appears in every integration status response, including disabled and invalid-configuration results. `integration_contract_version` in `/agent/capabilities` identifies the same contract. A breaking change to status fields, status meanings, or request semantics requires a new major version; additive optional fields may remain within the current major version.

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

Responses never include the external response body or configured URL. Probes disable environment proxy inheritance and redirects and use bounded streaming reads.

## Capability discovery

Authenticated `GET /agent/capabilities` provides a versioned, read-only inventory. Its `integrations` object reports each integration's enabled/configured state and status endpoint. Health remains `not_checked` until the corresponding status endpoint is explicitly called. Discovery does not probe networks, run inference, execute tools, download code, or activate capability sources.

## Ownership and security boundaries

- **HUB:** authentication, policy, approvals, audit records, durable jobs, workflow execution, model selection, and recovery.
- **Assistant runtime:** its own sessions, channels, plugins, and runtime state.
- **Code engine:** its own coding workspace and execution environment.
- **Adapters:** configuration validation and bounded, sanitized health checks only.

The services must not share a database or bypass HUB authorization. A future execution bridge requires a separately reviewed typed API contract, explicit permission mapping, approval gates, audit records, idempotency, and safe recovery. No arbitrary shell or code execution is exposed by these adapters.
