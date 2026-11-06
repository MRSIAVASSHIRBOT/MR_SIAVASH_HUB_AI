# Kimi K3.1 Pro Provider

The project includes optional text and single-image adapters for the official Kimi API. They are separate from OpenRouter and local Ollama inference.

## Enable explicitly

Set the following environment variables:

- `MRH_KIMI_INFERENCE_ENABLED=true`
- `MRH_KIMI_API_KEY=<Moonshot API key>`
- `MRH_KIMI_MODEL=kimi-k3.1-pro`
- `MRH_KIMI_REASONING_EFFORT=high` (one of `low`, `high`, `max`; the API default is `max`)
- `MRH_KIMI_TIMEOUT_SECONDS=60` (1–120 seconds)

The adapter uses the fixed official HTTPS origin `https://api.moonshot.ai/v1`, as specified by the [Kimi K3.1 Pro API quickstart](https://platform.kimi.ai/docs/guide/kimi-k3-1-pro-quickstart). The endpoint does not accept a user-configurable URL, preventing arbitrary-host credential forwarding. The key is held as a secret setting and is never returned by provider catalog endpoints.

## Explicit invocation

After configuration and API restart, use the authenticated endpoint:

- `POST /models/generate-kimi`
- JSON body: `{"input_text":"...","max_output_tokens":512}`

For a single image, call `POST /models/generate-kimi-vision` with `{"prompt":"Describe this image","image_data_url":"data:image/png;base64,...","max_output_tokens":512}`. The image must use a JPEG, PNG, or WebP data URL, pass base64 and media-signature validation, and decode to no more than 4 MiB. The endpoint does not fetch external URLs.

Both routes are opt-in and send submitted text and, for the vision route, image bytes to Moonshot. The vision route is an explicit endpoint and is not yet exposed through generic capability-based model selection; the provider catalog currently advertises the shared text capability only. Neither route is invoked by local inference, and neither silently falls back to Ollama, OpenRouter, or the test stub. A failed Kimi request returns a sanitized provider error.

The text endpoint is deliberately single-turn and uses the shared `ProviderRequest` contract (32,000 input characters; the HTTP route caps output at 2,048 tokens). The integration does not expose the model's full 1M-token context, video input, multi-turn preserved reasoning state, or tool execution. Multi-turn support must preserve the complete assistant message, including `reasoning_content`; that is not currently represented by the shared response contract.

## API model versus open weights

Kimi K3.1 Pro is an open-weight multimodal model and is also available through Moonshot's hosted API. The Hugging Face `moonshotai/Kimi-K3.1-Pro` model card documents the open-weight release and supported inference engines. This adapter uses only the hosted API; it does not download weights, launch a local inference server, or provision GPU resources. A separate local-provider integration can use a self-hosted OpenAI-compatible endpoint after its runtime, hardware, model license, and operational requirements are reviewed.

Review the official [Kimi API quickstart](https://platform.kimi.ai/docs/guide/kimi-k3-1-pro-quickstart), [Chat Completions API](https://platform.kimi.ai/docs/guide/kimi-k3-1-pro-quickstart), and [Hugging Face Kimi K3.1 Pro model card](https://huggingface.co/moonshotai/Kimi-K3.1-Pro) for current API behavior, model availability, pricing, hardware, and license requirements.

## Request rate limit

The authenticated Kimi text and vision endpoints share a per-owner sliding-window limit of 10 requests per 60 seconds. Request timestamps are stored in SQLite by schema migration 32, and each reservation uses an immediate write transaction so concurrent API processes using the same database file share one atomic quota. The quota survives API process restarts. Separate application instances that use separate database files do not share this limit; deployments spanning separate databases need a central distributed rate-limit service.

## Privacy and cost

Remote requests transfer submitted input text and, for vision calls, image bytes to Moonshot; both may incur usage charges. Do not send secrets, credentials, private source code, or personal data unless the owner has explicitly approved that data transfer. The model is not automatically selected for arbitrary tasks. Review current API pricing, account requirements, retention terms, and applicable terms before use.
