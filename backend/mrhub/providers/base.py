"""Typed provider contracts. Provider implementations must not log request content or secrets."""

import math
from dataclasses import dataclass
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator

from mrhub.providers.types import ModelDescriptor

MAX_PROVIDER_INPUT_CHARS = 32_000


class ProviderError(Exception):
    """Base provider error carrying only a stable, non-sensitive code."""

    code = "provider_error"


class ProviderUnavailableError(ProviderError):
    code = "provider_unavailable"


class ProviderConfigurationError(ProviderError):
    code = "provider_configuration"


class ProviderTimeoutError(ProviderError):
    code = "provider_timeout"


class ProviderContractError(ProviderError):
    """Raised when an adapter violates the selected model response contract."""

    code = "provider_contract_violation"


class ProviderRequest(BaseModel):
    """Bounded generation request with an optional adapter timeout ceiling.

    The timeout is enforced by the provider's HTTP client as per-phase network
    timeout behavior. It is not a wall-clock deadline for arbitrary local work,
    model inference progress, or an external side effect.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    input_text: str = Field(min_length=1, max_length=MAX_PROVIDER_INPUT_CHARS)
    max_output_tokens: int = Field(default=1024, ge=1, le=8192, strict=True)
    timeout_seconds: float | None = Field(default=None, ge=1.0, le=300.0)

    @field_validator("timeout_seconds", mode="before")
    @classmethod
    def validate_timeout(cls, value: object) -> object:
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError("Provider request timeout must be a finite number")
        try:
            finite = math.isfinite(float(value))
        except (OverflowError, ValueError):
            finite = False
        if not finite:
            raise ValueError("Provider request timeout must be a finite number")
        return value


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


def validate_provider_health(value: object) -> ProviderHealth:
    """Validate the runtime health contract shared by routing and diagnostics."""
    if (
        not isinstance(value, ProviderHealth)
        or type(value.available) is not bool
        or not isinstance(value.reason_code, str)
        or not value.reason_code
    ):
        raise ProviderContractError("Provider returned an invalid health contract")
    return value


class ModelProvider(Protocol):
    """Synchronous provider contract; adapters must honor request timeout caps.

    A request timeout bounds the adapter's HTTP operation. It does not promise
    to terminate arbitrary local handler code or undo a remote side effect.
    """

    descriptor: ModelDescriptor

    def generate(self, request: ProviderRequest) -> ProviderResponse:
        ...

    def health(self, timeout_seconds: float = 2.0) -> ProviderHealth:
        ...
