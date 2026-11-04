# Local integration health-probe contract

## Scope

The assistant-gateway and code-engine status endpoints use one shared, status-only probe. The probe does not execute commands, invoke model operations, read response bodies into API output, or treat a successful health check as proof that the integration is authorized for work.

## Request boundary

- Targets must use HTTP(S) and a literal IPv4/IPv6 loopback address. Hostnames, LAN addresses, credentials, query strings, and fragments are rejected.
- Health paths must be plain absolute paths. Encoded characters, traversal segments, duplicate separators, query strings, and absolute URLs are rejected.
- Redirects are not followed.
- Environment proxy settings are not inherited (trust_env=False).
- The timeout must be finite, greater than zero, and no more than 10 seconds.
- The response limit must be an integer from 1 through 16 KiB. The configured settings for each integration use a smaller default (8 KiB).
- The response stream is consumed only up to the configured limit. Its content is never returned or logged by this probe.

## Stable response states

Every probe response includes contract_version and status. configured indicates whether the target configuration passed validation and the probe was attempted.

| Status | Meaning |
|---|---|
| disabled | Integration feature flag is off; no probe is attempted |
| invalid_configuration | URL, path, timeout, or response limit failed validation |
| reachable | 2xx response received within limits |
| timeout | The HTTP client timed out |
| unreachable | Connection, protocol, or non-2xx failure |
| rejected_redirect | Server attempted to redirect the probe |
| response_too_large | Response exceeded the configured byte limit |

The response includes an HTTP status code only for ordinary non-2xx responses or successful 2xx responses. It never includes remote response content, exception text, credentials, or request headers.

## Cancellation and resource lifecycle

Task cancellation is intentionally not converted into an unreachable result. Callers and application shutdown logic must be able to cancel an in-flight probe. The HTTP client and streaming response are managed by async context managers so normal return, timeout, and cancellation release resources.

## Security and capability boundary

A reachable status endpoint proves only that a local HTTP endpoint responded. It does not prove identity, authorization, readiness for privileged work, compatibility of an execution protocol, or safety of code returned by the integration. Any future invocation adapter requires its own authenticated request contract, permission checks, request/response schemas, audit identity, and bounded execution policy.

## Validation

The test suite covers invalid targets, redirect refusal, proxy isolation, response-size enforcement, sanitized output, malformed paths, finite timeout bounds, timeout classification, and cancellation propagation. These probes remain loopback-only and status-only.
