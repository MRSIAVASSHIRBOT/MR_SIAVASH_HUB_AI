"""Explicit OpenRouter chat-completions adapter; never used as an implicit fallback."""
from __future__ import annotations

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


class OpenRouterProvider:
    """Optional remote text provider restricted to OpenRouter's HTTPS API origin."""

    def __init__(
        self,
        *,
        model: str,
        api_key: str,
        base_url: str = "https://openrouter.ai/api/v1",
        timeout_seconds: float = 30.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not model.strip() or len(model) > 200:
            raise ProviderConfigurationError("Invalid remote model name")
        if not api_key.strip() or len(api_key) > 1000:
            raise ProviderConfigurationError("Remote provider API key is missing or invalid")
        if not 1 <= timeout_seconds <= 120:
            raise ProviderConfigurationError("Remote timeout must be between 1 and 120 seconds")
        self.base_url = self._validate_base_url(base_url)
        self._api_key = api_key.strip()
        self.timeout_seconds = timeout_seconds
        self._transport = transport
        self.descriptor = ModelDescriptor(
            provider="openrouter",
            model=model.strip(),
            capability=ModelCapability(text=True),
            available=True,
            local=False,
            priority=50,
        )

    @staticmethod
    def _validate_base_url(value: str) -> str:
        try:
            parsed = urlsplit(value)
            hostname = (parsed.hostname or "").lower()
            if (
                parsed.scheme != "https"
                or hostname != "openrouter.ai"
                or parsed.username is not None
                or parsed.password is not None
                or parsed.path.rstrip("/") != "/api/v1"
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError
            port = parsed.port or 443
        except ValueError as exc:
            raise ProviderConfigurationError(
                "Remote provider URL must use the approved OpenRouter HTTPS API origin"
            ) from exc
        if port != 443:
            raise ProviderConfigurationError("Remote provider must use HTTPS port 443")
        return "https://openrouter.ai/api/v1/"

    def _client(self, timeout_seconds: float | None = None) -> httpx.Client:
        return httpx.Client(
            base_url=self.base_url,
            timeout=httpx.Timeout(timeout_seconds or self.timeout_seconds),
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            transport=self._transport,
            follow_redirects=False,
            trust_env=False,
        )

    @staticmethod
    def _token_count(value: object) -> int | None:
        return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None

    def health(self, timeout_seconds: float = 2.0) -> ProviderHealth:
        if not 0.1 <= timeout_seconds <= 10:
            raise ProviderConfigurationError("Health probe timeout must be between 0.1 and 10 seconds")
        try:
            with self._client(min(timeout_seconds, self.timeout_seconds)) as client:
                response = client.get("models")
            if 200 <= response.status_code < 300:
                return ProviderHealth(available=True, reason_code="provider_ready")
            return ProviderHealth(available=False, reason_code="provider_unavailable")
        except httpx.TimeoutException:
            return ProviderHealth(available=False, reason_code="provider_timeout")
        except httpx.HTTPError:
            return ProviderHealth(available=False, reason_code="provider_unavailable")

    def generate(self, request: ProviderRequest) -> ProviderResponse:
        try:
            with self._client() as client:
                response = client.post(
                    "chat/completions",
                    json={
                        "model": self.descriptor.model,
                        "messages": [{"role": "user", "content": request.input_text}],
                        "max_tokens": request.max_output_tokens,
                        "stream": False,
                    },
                )
            if not 200 <= response.status_code < 300:
                # Never include provider response bodies, headers, or key material in errors.
                raise ProviderUnavailableError("Remote model service returned an unavailable status")
            payload = response.json()
            if not isinstance(payload, dict):
                raise ProviderUnavailableError("Remote model returned an invalid response")
        except ProviderTimeoutError:
            raise
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError("Remote model request timed out") from exc
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError("Remote model service is unavailable") from exc
        except ValueError as exc:
            raise ProviderUnavailableError("Remote model returned an invalid response") from exc

        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            raise ProviderUnavailableError("Remote model returned an invalid response")
        message = choices[0].get("message")
        if not isinstance(message, dict):
            raise ProviderUnavailableError("Remote model returned an invalid response")
        output = message.get("content")
        if not isinstance(output, str) or len(output) > 100_000:
            raise ProviderUnavailableError("Remote model returned an invalid response")
        usage = payload.get("usage")
        if not isinstance(usage, dict):
            usage = {}
        choice_finish = choices[0].get("finish_reason")
        return ProviderResponse(
            provider=self.descriptor.provider,
            model=self.descriptor.model,
            output_text=output,
            input_tokens=self._token_count(usage.get("prompt_tokens")),
            output_tokens=self._token_count(usage.get("completion_tokens")),
            finish_reason=choice_finish if isinstance(choice_finish, str) else "stop",
        )
