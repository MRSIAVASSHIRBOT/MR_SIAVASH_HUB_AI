"""Explicit Moonshot Kimi K3.1 Pro adapter; no implicit provider fallback."""

from __future__ import annotations

import base64
import binascii
import json
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

_KIMI_BASE_URL = "https://api.moonshot.ai/v1/"
MAX_KIMI_RESPONSE_BYTES = 1_048_576
MAX_KIMI_HEALTH_RESPONSE_BYTES = 64 * 1024


class KimiProvider:
    """Call the official Kimi API with bounded text and inline-image requests."""

    def __init__(
        self,
        *,
        model: str,
        api_key: str,
        reasoning_effort: str = "high",
        timeout_seconds: float = 60.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not model.strip() or len(model) > 200:
            raise ProviderConfigurationError("Invalid Kimi model name")
        if not api_key.strip() or len(api_key) > 1000:
            raise ProviderConfigurationError("Kimi API key is missing or invalid")
        if reasoning_effort not in {"low", "high", "max"}:
            raise ProviderConfigurationError("Invalid Kimi reasoning effort")
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, (int, float))
            or not 1 <= timeout_seconds <= 120
        ):
            raise ProviderConfigurationError("Kimi timeout must be between 1 and 120 seconds")

        self.base_url = self._validate_base_url(_KIMI_BASE_URL)
        self._api_key = api_key.strip()
        self.reasoning_effort = reasoning_effort
        self.timeout_seconds = timeout_seconds
        self._transport = transport
        self.descriptor = ModelDescriptor(
            provider="moonshot",
            model=model.strip(),
            capability=ModelCapability(text=True),
            available=True,
            local=False,
            priority=40,
        )

    @staticmethod
    def _validate_base_url(value: str) -> str:
        """Keep credentials pinned to Moonshot's official HTTPS API origin."""
        try:
            parsed = urlsplit(value)
            if (
                parsed.scheme != "https"
                or (parsed.hostname or "").lower() != "api.moonshot.ai"
                or parsed.username is not None
                or parsed.password is not None
                or parsed.path.rstrip("/") != "/v1"
                or parsed.query
                or parsed.fragment
                or (parsed.port or 443) != 443
            ):
                raise ValueError
        except ValueError as exc:
            raise ProviderConfigurationError("Kimi API origin is not approved") from exc
        return _KIMI_BASE_URL

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
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            return value
        return None

    def _post_json(self, body: dict[str, object]) -> dict[str, object]:
        """Read a provider response incrementally and enforce a hard byte ceiling."""
        try:
            content = bytearray()
            with (
                self._client() as client,
                client.stream("POST", "chat/completions", json=body) as response,
            ):
                if not 200 <= response.status_code < 300:
                    raise ProviderUnavailableError(
                        "Kimi service returned an unavailable status"
                    )
                for chunk in response.iter_bytes():
                    if len(content) + len(chunk) > MAX_KIMI_RESPONSE_BYTES:
                        raise ProviderUnavailableError(
                            "Kimi response exceeded the size limit"
                        )
                    content.extend(chunk)
            payload = json.loads(content)
            if not isinstance(payload, dict):
                raise ProviderUnavailableError("Kimi returned an invalid response")
            return payload
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError("Kimi request timed out") from exc
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError("Kimi service is unavailable") from exc
        except (ValueError, UnicodeError) as exc:
            raise ProviderUnavailableError("Kimi returned an invalid response") from exc

    def health(self, timeout_seconds: float = 2.0) -> ProviderHealth:
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, (int, float))
            or not 0.1 <= timeout_seconds <= 10
        ):
            raise ProviderConfigurationError(
                "Health probe timeout must be between 0.1 and 10 seconds"
            )
        try:
            with (
                self._client(min(timeout_seconds, self.timeout_seconds)) as client,
                client.stream("GET", "models") as response,
            ):
                if not 200 <= response.status_code < 300:
                    return ProviderHealth(
                        available=False, reason_code="provider_unavailable"
                    )
                response_bytes = 0
                for chunk in response.iter_bytes():
                    response_bytes += len(chunk)
                    if response_bytes > MAX_KIMI_HEALTH_RESPONSE_BYTES:
                        return ProviderHealth(
                            available=False, reason_code="provider_unavailable"
                        )
            return ProviderHealth(available=True, reason_code="provider_ready")
        except httpx.TimeoutException:
            return ProviderHealth(available=False, reason_code="provider_timeout")
        except httpx.HTTPError:
            return ProviderHealth(available=False, reason_code="provider_unavailable")

    def generate_vision(
        self,
        *,
        prompt: str,
        image_data_url: str,
        max_output_tokens: int = 512,
    ) -> ProviderResponse:
        """Analyze one bounded inline image; arbitrary remote URLs are never fetched."""
        if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 8_000:
            raise ProviderConfigurationError("Vision prompt must contain 1 to 8000 characters")
        if not isinstance(image_data_url, str) or len(image_data_url) > 5_600_000:
            raise ProviderConfigurationError("Image data URL is missing or exceeds the size limit")
        if (
            not isinstance(max_output_tokens, int)
            or isinstance(max_output_tokens, bool)
            or not 1 <= max_output_tokens <= 2048
        ):
            raise ProviderConfigurationError("Vision output token limit must be between 1 and 2048")

        prefixes = {
            "data:image/jpeg;base64,": lambda data: data.startswith(b"\xff\xd8\xff"),
            "data:image/png;base64,": lambda data: data.startswith(b"\x89PNG\r\n\x1a\n"),
            "data:image/webp;base64,": (
                lambda data: len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP"
            ),
        }
        selected = next(
            ((prefix, check) for prefix, check in prefixes.items()
             if image_data_url.startswith(prefix)),
            None,
        )
        if selected is None:
            raise ProviderConfigurationError(
                "Only JPEG, PNG, and WebP base64 data URLs are accepted"
            )
        prefix, signature_check = selected
        encoded = image_data_url[len(prefix):]
        try:
            image_bytes = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ProviderConfigurationError("Image data URL contains invalid base64") from exc
        if not image_bytes or len(image_bytes) > 4 * 1024 * 1024:
            raise ProviderConfigurationError("Decoded image must be no larger than 4 MiB")
        if not signature_check(image_bytes):
            raise ProviderConfigurationError("Image bytes do not match the declared media type")

        payload = self._post_json(
            {
                "model": self.descriptor.model,
                "messages": [{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": image_data_url}},
                    ],
                }],
                "max_completion_tokens": max_output_tokens,
                "reasoning_effort": self.reasoning_effort,
                "stream": False,
            }
        )

        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            raise ProviderUnavailableError("Kimi returned an invalid response")
        message = choices[0].get("message")
        if not isinstance(message, dict):
            raise ProviderUnavailableError("Kimi returned an invalid response")
        output = message.get("content")
        if not isinstance(output, str) or not output.strip() or len(output) > 100_000:
            raise ProviderUnavailableError("Kimi returned an invalid response")
        usage = payload.get("usage")
        if not isinstance(usage, dict):
            usage = {}
        finish_reason = choices[0].get("finish_reason")
        return ProviderResponse(
            provider=self.descriptor.provider,
            model=self.descriptor.model,
            output_text=output,
            input_tokens=self._token_count(usage.get("prompt_tokens")),
            output_tokens=self._token_count(usage.get("completion_tokens")),
            finish_reason=finish_reason if isinstance(finish_reason, str) else "stop",
        )

    def generate(self, request: ProviderRequest) -> ProviderResponse:
        payload = self._post_json(
            {
                "model": self.descriptor.model,
                "messages": [{"role": "user", "content": request.input_text}],
                "max_completion_tokens": request.max_output_tokens,
                "reasoning_effort": self.reasoning_effort,
                "stream": False,
            }
        )

        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            raise ProviderUnavailableError("Kimi returned an invalid response")
        message = choices[0].get("message")
        if not isinstance(message, dict):
            raise ProviderUnavailableError("Kimi returned an invalid response")
        output = message.get("content")
        if not isinstance(output, str) or not output.strip() or len(output) > 100_000:
            raise ProviderUnavailableError("Kimi returned an invalid response")
        usage = payload.get("usage")
        if not isinstance(usage, dict):
            usage = {}
        finish_reason = choices[0].get("finish_reason")
        return ProviderResponse(
            provider=self.descriptor.provider,
            model=self.descriptor.model,
            output_text=output,
            input_tokens=self._token_count(usage.get("prompt_tokens")),
            output_tokens=self._token_count(usage.get("completion_tokens")),
            finish_reason=finish_reason if isinstance(finish_reason, str) else "stop",
        )
