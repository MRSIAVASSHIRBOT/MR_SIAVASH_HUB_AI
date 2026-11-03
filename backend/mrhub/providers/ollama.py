"""Loopback-only Ollama adapter with bounded synchronous HTTP requests."""

from urllib.parse import urlsplit

import httpx

from mrhub.providers.base import (
    ProviderConfigurationError,
    ProviderHealth,
    ProviderRequest,
    ProviderResponse,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from mrhub.providers.types import ModelCapability, ModelDescriptor


class OllamaProvider:
    """Connect to an explicitly configured Ollama server on the local machine only."""

    def __init__(
        self,
        model: str,
        base_url: str = "http://127.0.0.1:11434",
        timeout_seconds: float = 60.0,
        transport: httpx.BaseTransport | None = None,
        vision_enabled: bool = False,
    ) -> None:
        if not model.strip() or len(model) > 200:
            raise ProviderConfigurationError("Invalid local model name")
        if not 1 <= timeout_seconds <= 300:
            raise ProviderConfigurationError("Timeout must be between 1 and 300 seconds")
        self.base_url = self._validate_loopback_url(base_url)
        self.timeout_seconds = timeout_seconds
        self._transport = transport
        self.descriptor = ModelDescriptor(
            provider="ollama",
            model=model.strip(),
            capability=ModelCapability(text=True, vision=vision_enabled),
            available=True,
            local=True,
            priority=10,
        )

    @staticmethod
    def _validate_loopback_url(value: str) -> str:
        try:
            parsed = urlsplit(value)
            hostname = (parsed.hostname or "").lower()
            if (
                parsed.scheme != "http"
                or hostname not in {"localhost", "127.0.0.1", "::1"}
                or parsed.username is not None
                or parsed.password is not None
                or parsed.path not in {"", "/"}
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError
            port = parsed.port or 11434
        except ValueError as exc:
            raise ProviderConfigurationError(
                "Local provider URL must be a plain HTTP loopback address"
            ) from exc
        if not 1 <= port <= 65535:
            raise ProviderConfigurationError("Invalid local provider port")
        host = f"[{hostname}]" if ":" in hostname else hostname
        return f"http://{host}:{port}"

    def _client(self, timeout_seconds: float | None = None) -> httpx.Client:
        return httpx.Client(
            base_url=self.base_url,
            timeout=httpx.Timeout(timeout_seconds or self.timeout_seconds),
            transport=self._transport,
            follow_redirects=False,
            trust_env=False,
        )

    def health(self, timeout_seconds: float = 2.0) -> ProviderHealth:
        if not 0.1 <= timeout_seconds <= 10:
            raise ProviderConfigurationError("Health probe timeout must be between 0.1 and 10 seconds")
        try:
            with self._client(min(timeout_seconds, self.timeout_seconds)) as client:
                response = client.get("/api/tags")
                response.raise_for_status()
            return ProviderHealth(available=True, reason_code="ollama_ready")
        except httpx.TimeoutException:
            return ProviderHealth(available=False, reason_code="provider_timeout")
        except (httpx.HTTPError, ValueError):
            return ProviderHealth(available=False, reason_code="provider_unavailable")

    def generate(self, request: ProviderRequest) -> ProviderResponse:
        if request.images and not self.descriptor.capability.vision:
            raise ProviderConfigurationError("Vision is not enabled for this local model")
        try:
            with self._client() as client:
                response = client.post(
                    "/api/generate",
                    json={
                        "model": self.descriptor.model,
                        "prompt": request.input_text,
                        **({"images": [item.data_base64 for item in request.images]} if request.images else {}),
                        "stream": False,
                        "options": {"num_predict": request.max_output_tokens},
                    },
                )
                response.raise_for_status()
                payload = response.json()
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError("Local model request timed out") from exc
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError("Local model service is unavailable") from exc
        except ValueError as exc:
            raise ProviderUnavailableError("Local model returned an invalid response") from exc

        output = payload.get("response")
        if not isinstance(output, str) or len(output) > 100_000:
            raise ProviderUnavailableError("Local model returned an invalid response")
        return ProviderResponse(
            provider=self.descriptor.provider,
            model=self.descriptor.model,
            output_text=output,
            input_tokens=payload.get("prompt_eval_count"),
            output_tokens=payload.get("eval_count"),
            finish_reason=str(payload.get("done_reason") or "stop"),
        )
