"""Typed provider contracts. Provider implementations must not log request content or secrets."""

import base64
import binascii
from dataclasses import dataclass
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from mrhub.providers.types import ModelDescriptor


class ProviderError(Exception):
    """Base provider error carrying only a stable, non-sensitive code."""

    code = "provider_error"


class ProviderUnavailableError(ProviderError):
    code = "provider_unavailable"


class ProviderConfigurationError(ProviderError):
    code = "provider_configuration"


class ProviderTimeoutError(ProviderError):
    code = "provider_timeout"


class ImageInput(BaseModel):
    """Bounded inline image. Paths and remote URLs are deliberately unsupported."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    mime_type: str
    data_base64: str = Field(min_length=16, max_length=5_600_000)

    @field_validator("mime_type")
    @classmethod
    def validate_mime_type(cls, value: str) -> str:
        if value not in {"image/jpeg", "image/png", "image/webp"}:
            raise ValueError("Unsupported image MIME type")
        return value

    @field_validator("data_base64")
    @classmethod
    def validate_image_bytes(cls, value: str, info) -> str:
        try:
            raw = base64.b64decode(value, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError("Image data must be valid base64") from exc
        if not raw or len(raw) > 4 * 1024 * 1024:
            raise ValueError("Image payload exceeds the 4 MiB limit")
        mime = info.data.get("mime_type")
        signatures = {
            "image/jpeg": raw.startswith(b"\xff\xd8\xff"),
            "image/png": raw.startswith(b"\x89PNG\r\n\x1a\n"),
            "image/webp": len(raw) >= 12 and raw.startswith(b"RIFF") and raw[8:12] == b"WEBP",
        }
        if mime not in signatures or not signatures[mime]:
            raise ValueError("Image bytes do not match the declared MIME type")
        return value


class ProviderRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    input_text: str = Field(min_length=1, max_length=32_000)
    max_output_tokens: int = Field(default=1024, ge=1, le=8192)
    images: tuple[ImageInput, ...] = Field(default=(), max_length=4)

    @model_validator(mode="after")
    def validate_image_budget(self):
        total = sum(len(item.data_base64) for item in self.images)
        if total > 10_700_000:
            raise ValueError("Combined image payload exceeds the 8 MiB limit")
        return self


class ProviderResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    provider: str
    model: str
    output_text: str
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    finish_reason: str = "stop"


@dataclass(frozen=True)
class ProviderHealth:
    available: bool
    reason_code: str


class ModelProvider(Protocol):
    """Synchronous provider contract; implementations must enforce their own timeout."""

    descriptor: ModelDescriptor

    def generate(self, request: ProviderRequest) -> ProviderResponse:
        ...

    def health(self, timeout_seconds: float = 2.0) -> ProviderHealth:
        ...
