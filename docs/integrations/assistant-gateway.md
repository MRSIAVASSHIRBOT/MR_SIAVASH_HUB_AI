# Optional Assistant Gateway Integration

**Status:** Initial implementation on a feature branch. The bridge is disabled by default and currently supports a bounded local health check only.

## Goal

Allow the HUB to detect an explicitly configured, separately managed local assistant runtime without coupling the runtime to the HUB's core process. The connector is intentionally small: it does not install or launch external software, execute remote tools, route prompts, or publish messages.

## Ownership boundaries

- **HUB:** authentication, policy, approvals, audit records, durable jobs, workflow execution, model selection, and recovery.
- **External runtime:** its own sessions, channels, plugins, and runtime state.
- **Connector:** configuration validation, loopback-only health probing, bounded timeouts, response-size limits, and sanitized status reporting.

The systems must not share a database or bypass one another's authorization boundaries.

## Current implementation

Authenticated endpoint:

`GET /integrations/assistant-gateway/status`

Possible statuses include:

- `disabled`: the connector is disabled; no outbound request is made.
- `invalid_configuration`: the URL or health path does not pass validation.
- `reachable`: the configured health endpoint returned a successful response within the response-size limit.
- `unreachable`: the request failed or returned a non-success status.
- `rejected_redirect`: the endpoint attempted to redirect the request.
- `response_too_large`: the response exceeded the configured limit.

The connector accepts only an HTTP(S) URL with a literal loopback IP address. It disables environment proxy inheritance and redirects, bounds the timeout and response body, and never returns the external response body to the caller.

## Configuration

The connector is disabled by default. Configure these environment variables only after manually setting up a compatible local runtime:

- `MRH_ASSISTANT_GATEWAY_ENABLED=false`
- `MRH_ASSISTANT_GATEWAY_BASE_URL` — local loopback URL only.
- `MRH_ASSISTANT_GATEWAY_HEALTH_PATH=/health`
- `MRH_ASSISTANT_GATEWAY_TIMEOUT_SECONDS=2`
- `MRH_ASSISTANT_GATEWAY_MAX_RESPONSE_BYTES=8192`

Do not place credentials in source control. If the chosen runtime requires authentication, a later change must add a documented secret-based mechanism rather than putting credentials in the URL.

## Security constraints

1. No automatic download, installation, process launch, or plugin activation.
2. No non-loopback endpoint by default.
3. No redirect following, proxy inheritance, unbounded response bodies, or unbounded request time.
4. No arbitrary tool execution or outbound messaging through this initial bridge.
5. No silent fallback between local and remote model providers.
6. All future task submission must use authenticated HUB APIs, existing policy checks, durable jobs, idempotency, and required approvals.
7. External side effects must be audited and must not be blindly retried when the result is ambiguous.

## Next stages

1. Run the project's test suite and CI on this branch.
2. Confirm the exact health/API contract and version compatibility of the manually installed runtime.
3. Add a typed, read-only capability-discovery interface.
4. Add a narrowly scoped task bridge only after compatibility and policy tests pass.
5. Consider channel actions only after destination allowlists, duplicate-send protection, audit records, and approval gates are in place.

This initial change is not a claim that full assistant-runtime integration is complete.

## HUB capability discovery

The authenticated endpoint `GET /agent/capabilities` returns a versioned, read-only inventory for the HUB's current orchestration layer:

- `models`: configured model descriptors and declared text, vision, audio, and tool-calling capabilities.
- `tools`: registered tool names, descriptions, input/output JSON schemas, risk classes, required permissions, and external-side-effect flags.
- `capability_sources`: reviewed catalog entries whose status is `approved`; approval in this catalog does not install or activate code.
- `assistant_gateway`: whether the optional gateway is enabled/configured; health remains `not_checked` until a separate explicit health request.

The response includes `schema_version`, `discovery_mode=read_only`, and explicit false flags for execution, network probes, and downloads. This endpoint does not contact the external gateway, run model inference, invoke tools, or activate capability sources. Consumers should ignore unknown fields and require a supported schema version before relying on the contract.
