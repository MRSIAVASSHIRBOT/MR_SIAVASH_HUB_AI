"""Bounded image-input provider contracts and local Ollama vision adapter."""

from __future__ import annotations

import base64
import json
import math
from dataclasses import dataclass
from typing import Protocol

import httpx

from mrhub.providers.base import (
    ProviderConfigurationError,
    ProviderHealth,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from mrhub.providers.ollama import OllamaProvider
from mrhub.providers.types import ModelCapability, ModelDescriptor

MAX_VISION_IMAGES = 12
MAX_VISION_IMAGE_BYTES = 1_500_000
MAX_VISION_TOTAL_BYTES = 12_000_000
MAX_VISION_PROMPT_CHARS = 8_000
MAX_VISION_OUTPUT_CHARS = 20_000
MAX_VISION_RESPONSE_BYTES = 64 * 1024


@dataclass(frozen=True, slots=True)
class VisionImage:
    """A transient JPEG image tied to a timestamp measured by the media pipeline."""

    timestamp_seconds: float
    jpeg_bytes: bytes

    def __post_init__(self) -> None:
        if (
            not isinstance(self.timestamp_seconds, (int, float))
            or isinstance(self.timestamp_seconds, bool)
            or not math.isfinite(self.timestamp_seconds)
            or not 0 <= self.timestamp_seconds <= 60
        ):
            raise ValueError("Vision image timestamp is outside the supported range")
        if not isinstance(self.jpeg_bytes, bytes) or not 0 < len(self.jpeg_bytes) <= MAX_VISION_IMAGE_BYTES:
            raise ValueError("Vision image must be a bounded non-empty JPEG byte string")


@dataclass(frozen=True, slots=True)
class VisionRequest:
    """Bounded prompt and transient frame batch for one local vision inference."""

    prompt: str
    images: tuple[VisionImage, ...]
    max_output_tokens: int = 1024

    def __post_init__(self) -> None:
        if not isinstance(self.prompt, str) or not 1 <= len(self.prompt) <= MAX_VISION_PROMPT_CHARS:
            raise ValueError("Vision prompt is empty or too large")
        if not 1 <= len(self.images) <= MAX_VISION_IMAGES:
            raise ValueError("Vision request must contain between 1 and 12 images")
        if (
            not isinstance(self.max_output_tokens, int)
            or isinstance(self.max_output_tokens, bool)
            or not 1 <= self.max_output_tokens <= 2048
        ):
            raise ValueError("Vision output token limit is outside the supported range")
        if sum(len(image.jpeg_bytes) for image in self.images) > MAX_VISION_TOTAL_BYTES:
            raise ValueError("Vision image batch exceeds the aggregate byte limit")
        timestamps = [image.timestamp_seconds for image in self.images]
        if timestamps != sorted(set(timestamps)):
            raise ValueError("Vision image timestamps must be unique and ordered")


@dataclass(frozen=True, slots=True)
class VisionResponse:
    provider: str
    model: str
    output_text: str

    def __post_init__(self) -> None:
        if not isinstance(self.provider, str) or not 1 <= len(self.provider) <= 80:
            raise ValueError("Vision response provider is invalid")
        if not isinstance(self.model, str) or not 1 <= len(self.model) <= 200:
            raise ValueError("Vision response model is invalid")
        if (
            not isinstance(self.output_text, str)
            or not self.output_text.strip()
            or len(self.output_text) > MAX_VISION_OUTPUT_CHARS
        ):
            raise ValueError("Vision response text is empty or too large")


class VisionProvider(Protocol):
    """Provider contract kept separate from text-only ModelProvider."""

    descriptor: ModelDescriptor

    def generate(self, request: VisionRequest) -> VisionResponse:
        ...

    def health(self, timeout_seconds: float = 2.0) -> ProviderHealth:
        ...


class OllamaVisionProvider:
    """Local-only Ollama vision adapter with strict input/output and timeout bounds."""

    def __init__(
        self,
        model: str,
        base_url: str = "http://127.0.0.1:11434",
        timeout_seconds: float = 120.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not model.strip() or len(model) > 200:
            raise ProviderConfigurationError("Invalid local vision model name")
        if not 1 <= timeout_seconds <= 180:
            raise ProviderConfigurationError("Vision timeout must be between 1 and 180 seconds")
        self.base_url = OllamaProvider._validate_loopback_url(base_url)
        self.timeout_seconds = timeout_seconds
        self._transport = transport
        self.descriptor = ModelDescriptor(
            provider="ollama",
            model=model.strip(),
            capability=ModelCapability(text=True, vision=True),
            available=True,
            local=True,
            priority=10,
        )

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
            return ProviderHealth(available=True, reason_code="ollama_vision_ready")
        except httpx.TimeoutException:
            return ProviderHealth(available=False, reason_code="provider_timeout")
        except (httpx.HTTPError, ValueError):
            return ProviderHealth(available=False, reason_code="provider_unavailable")

    def generate(self, request: VisionRequest) -> VisionResponse:
        if not isinstance(request, VisionRequest):
            raise ProviderConfigurationError("Invalid vision request")
        images = [
            base64.b64encode(image.jpeg_bytes).decode("ascii")
            for image in request.images
        ]
        try:
            with self._client() as client:
                with client.stream(
                    "POST",
                    "/api/generate",
                    json={
                        "model": self.descriptor.model,
                        "prompt": request.prompt,
                        "images": images,
                        "stream": False,
                        "options": {"num_predict": request.max_output_tokens},
                    },
                ) as response:
                    response.raise_for_status()
                    body = bytearray()
                    for chunk in response.iter_bytes():
                        if len(body) + len(chunk) > MAX_VISION_RESPONSE_BYTES:
                            raise ProviderUnavailableError(
                                "Local vision model response exceeded the size limit"
                            )
                        body.extend(chunk)
                payload = json.loads(body)
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError("Local vision request timed out") from exc
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError("Local vision service is unavailable") from exc
        except (ValueError, UnicodeDecodeError) as exc:
            raise ProviderUnavailableError("Local vision model returned an invalid response") from exc

        output = payload.get("response") if isinstance(payload, dict) else None
        if not isinstance(output, str) or not output.strip() or len(output) > MAX_VISION_OUTPUT_CHARS:
            raise ProviderUnavailableError("Local vision model returned an invalid response")
        return VisionResponse(
            provider=self.descriptor.provider,
            model=self.descriptor.model,
            output_text=output,
        )
