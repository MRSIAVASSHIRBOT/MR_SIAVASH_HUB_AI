"""Typed provider contracts. Provider implementations must not log request content or secrets."""

from dataclasses import dataclass
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

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
    model_config = ConfigDict(frozen=True)

    input_text: str = Field(min_length=1, max_length=MAX_PROVIDER_INPUT_CHARS)
    max_output_tokens: int = Field(default=1024, ge=1, le=8192)


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
    """Synchronous provider contract; implementations must enforce their own timeout."""

    descriptor: ModelDescriptor

    def generate(self, request: ProviderRequest) -> ProviderResponse:
        ...

    def health(self, timeout_seconds: float = 2.0) -> ProviderHealth:
        ...
