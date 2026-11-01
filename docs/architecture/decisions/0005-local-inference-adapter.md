# ADR 0005: Loopback-only local inference adapter

## Status
Accepted for the initial local inference integration.

## Context
The model provider contract exists, but no adapter performs inference. The first real adapter should support a free local runtime without introducing cloud dependencies or weakening the local-first policy.

## Decision
- Integrate Ollama through its local HTTP API.
- Only permit plain HTTP loopback URLs: `localhost`, `127.0.0.1`, and `::1`.
- Disable local inference by default. Activation requires explicit environment configuration and a named model.
- Disable redirects and environment-proxy inheritance in the HTTP client.
- Use non-streaming generation, finite request timeout, and bounded output-token settings.
- Expose generation only through the authenticated API.
- Return sanitized provider error codes; never log request content, credentials, or raw server errors.
- Never fall back from a failed local provider to a remote provider.
- Do not download models, launch processes, or change the user's machine automatically.

## Consequences
The application can connect to a locally installed Ollama instance when the owner explicitly enables it. Ollama and a model must be installed separately. Resource use depends on model size and machine capacity; benchmark before selecting a model for routine use.
