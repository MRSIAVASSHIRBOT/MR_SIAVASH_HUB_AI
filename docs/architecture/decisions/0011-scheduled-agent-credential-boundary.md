# ADR-0011: Credential boundary for scheduled development agents

- Status: Accepted for the current GitHub-hosted scheduled-agent threat model
- Date: 2026-11-19
- Related: Issues #316 and #332

## Context

The scheduled development workflow uses OpenCode to propose small repository changes. The model provider requires an OpenRouter credential, but the agent-controlled tools and project configuration must not receive or expose that credential.

A default-deny tool policy is necessary but is not, by itself, a credential-isolation boundary. The workflow therefore uses a separate credential broker and a non-secret local token.

## Decision

Keep the provider credential in the trusted broker process and do not pass it in the OpenCode process environment.

The workflow must preserve all of these controls:

1. The credential is injected only into the broker process invocation.
2. The parent shell unsets `OPENROUTER_API_KEY` before launching OpenCode.
3. OpenCode is configured with the fixed loopback broker URL and a non-secret broker token.
4. The broker binds only to `127.0.0.1`, accepts only loopback clients, requires its local token, and exposes only the approved model-list and chat-completion routes.
5. Chat completion requests are restricted to the configured free model; the broker fixes the upstream host to HTTPS `openrouter.ai`, constructs upstream headers itself, rejects redirects, bounds request/response sizes, and suppresses access logs.
6. OpenCode uses a default-deny permission policy. Shell, task/subagent, skills, MCP, web, content-search, LSP, and external-directory access remain denied. Only the required workspace read/write and path-discovery operations are enabled.
7. The publisher runs in a separate job with write permissions. It receives only a patch artifact, validates normalized staged paths and rejects symlinks/submodules before applying it. Agent-controlled workflow, security, dependency, and publisher paths remain protected.
8. The publisher creates a review PR; it never merges the agent proposal automatically.

## Threat model and residual risk

This boundary is accepted for the current scheduled workflow because the agent has no shell or arbitrary tool execution, receives no provider credential in its environment, and can reach only the broker's narrowly allowlisted API surface through the configured provider.

This is **not** a claim of a separate OS user, VM, container, kernel, or hardware security boundary. The broker and OpenCode execute on the same ephemeral GitHub-hosted runner. A compromised OpenCode binary/runtime, a host-level compromise, or a future permission/configuration regression could exceed the current threat model. The broker's static local token is a capability for the restricted broker API, not a substitute for OS isolation.

If the threat model is expanded to include a compromised agent runtime or hostile code execution inside the agent process, do not reuse this acceptance. Move the agent into a separately isolated container/VM with a narrowly scoped broker channel and independently enforced egress policy, then add adversarial integration tests before enabling scheduled publication.

The model provider necessarily receives prompts and repository context sent for inference. Never place credentials, private user data, or unrelated sensitive material in the scheduled agent workspace or prompt.

## Verification requirements

- Workflow policy validation must pass on the exact main SHA.
- Regression tests must verify the secret is assigned only to the broker, is unset before OpenCode starts, and OpenCode uses only the loopback broker configuration.
- Broker tests must verify loopback binding, local-token authentication, route/method allowlists, fixed upstream host, fixed model, redirect rejection, bounded payloads, and suppression of request logging.
- The publisher must validate the staged patch before its write token is made available.
- A failed/expired provider credential must fail closed. It must not trigger a fallback provider or publish a patch.

## Operational follow-up

Issue #332 remains owner-dependent: the repository's expired provider credential must be renewed through GitHub repository/environment secret settings. Do not request, read, paste, or rotate the secret through chat or source code.

This ADR accepts the present boundary only for the stated threat model; it does not authorize running the scheduled publisher until the credential is valid and the exact-head security and CI gates pass.
