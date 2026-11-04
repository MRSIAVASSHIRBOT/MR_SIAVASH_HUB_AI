# Explicit Remote Model Inference

The initial remote adapter supports OpenRouter's OpenAI-compatible chat-completions API. It is opt-in and separate from the local-only `POST /models/generate` endpoint.

## Configuration

Set these environment variables only when you explicitly choose to enable remote inference:

- `MRH_REMOTE_INFERENCE_ENABLED=true`
- `MRH_REMOTE_INFERENCE_API_KEY=<your key>`
- `MRH_REMOTE_INFERENCE_MODEL=<explicit provider model ID>`
- `MRH_REMOTE_INFERENCE_BASE_URL=https://openrouter.ai/api/v1`
- `MRH_REMOTE_INFERENCE_TIMEOUT_SECONDS=30` (1–120 seconds)

The adapter rejects non-HTTPS, non-OpenRouter origins, redirects, custom ports, and URLs containing credentials, query strings, or fragments. API keys are kept in environment configuration, never returned by the API, and are not included in error messages or logs.

## Explicit invocation and fallback behavior

- `POST /models/generate-remote` sends one authenticated request through a remote-only `ModelRouter`; the local Ollama adapter and Stub are excluded from this route.
- If remote inference is disabled or incompletely configured, the endpoint returns a sanitized 503 and makes no provider request.
- The shared router performs its bounded provider-health gate before inference and validates that the returned value is a `ProviderResponse` whose provider/model identity matches the selected descriptor. Contract violations return the stable `provider_contract_violation` error.
- If the remote provider fails, the endpoint returns a sanitized provider error. It never retries through the local stub, Ollama, or another cloud provider.
- `GET /models/providers` does not perform health checks or inference. The explicit health-check endpoint remains available for standalone provider diagnostics.

## Cost and privacy

Remote inference sends the submitted input text to OpenRouter. Do not submit sensitive data unless your policy explicitly allows that transfer. Some provider models may be labeled free, but that label is not a promise of permanent availability, unlimited usage, no account requirement, or zero cost. Check the current model terms and pricing before enabling the adapter. It is disabled by default, and the project does not choose a remote model automatically.

This adapter supports text only. It does not grant tools, perform external publishing, download models, or change workflow approval policy.
