"""Capability-aware model selection and explicit provider dispatch."""

from pydantic import BaseModel, ConfigDict

from mrhub.providers.base import (
    ModelProvider,
    ProviderContractError,
    ProviderHealth,
    ProviderRequest,
    ProviderResponse,
)
from mrhub.providers.registry import ProviderRegistry
from mrhub.providers.types import ModelCapability, ModelDescriptor

__all__ = ["ModelCapability", "ModelDescriptor", "ModelRequest", "ModelRouter", "ModelSelection"]


class ModelRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    requires_text: bool = True
    requires_vision: bool = False
    requires_audio: bool = False
    requires_tool_calling: bool = False
    prefer_local: bool = False


class ModelSelection(BaseModel):
    provider: str
    model: str
    local: bool
    rationale: str


class ModelRouter:
    """Selects registered descriptors; dispatch occurs only via explicit adapters."""

    def __init__(self, registry: ProviderRegistry | None = None) -> None:
        self._providers: dict[tuple[str, str], ModelDescriptor] = {}
        # Preserve the caller's registry as the single adapter authority,
        # including registry implementations that intentionally evaluate false.
        self.registry = registry if registry is not None else ProviderRegistry()

    def register(self, descriptor: ModelDescriptor) -> None:
        key = (descriptor.provider, descriptor.model)
        if key in self._providers:
            raise ValueError("Model descriptor is already registered")
        self._providers[key] = descriptor

    def register_provider(self, provider: ModelProvider) -> None:
        descriptor = provider.descriptor
        key = (descriptor.provider, descriptor.model)
        if key in self._providers:
            raise ValueError("Model descriptor is already registered")
        # Check the router catalog before mutating the adapter registry so a
        # duplicate descriptor cannot leave the two registries out of sync.
        self.registry.register(provider)
        self._providers[key] = descriptor

    def catalog(self) -> list[ModelDescriptor]:
        return sorted(
            (item for item in self._providers.values() if item.available),
            key=lambda item: (not item.local, item.priority, item.provider, item.model),
        )

    def select(self, request: ModelRequest) -> ModelSelection:
        candidates = [item for item in self._providers.values() if item.available]
        if request.requires_text:
            candidates = [item for item in candidates if item.capability.text]
        if request.requires_vision:
            candidates = [item for item in candidates if item.capability.vision]
        if request.requires_audio:
            candidates = [item for item in candidates if item.capability.audio]
        if request.requires_tool_calling:
            candidates = [item for item in candidates if item.capability.tool_calling]
        if request.prefer_local:
            candidates = [item for item in candidates if item.local]
        if not candidates:
            raise LookupError("No available model satisfies the requested capabilities")
        selected = min(
            candidates,
            key=lambda item: (
                not item.local if request.prefer_local else False,
                item.priority,
                item.provider,
                item.model,
            ),
        )
        return ModelSelection(
            provider=selected.provider,
            model=selected.model,
            local=selected.local,
            rationale="Selected from registered available models by capability and priority",
        )

    def generate(self, request: ModelRequest, payload: ProviderRequest) -> ProviderResponse:
        selection = self.select(request)
        provider = self.registry.get(selection.provider, selection.model)
        health = provider.health(timeout_seconds=2.0)
        if (
            not isinstance(health, ProviderHealth)
            or type(health.available) is not bool
            or not isinstance(health.reason_code, str)
            or not health.reason_code
        ):
            raise ProviderContractError("Provider returned an invalid health contract")
        if not health.available:
            raise LookupError("Selected provider is unavailable")

        response = provider.generate(payload)
        if not isinstance(response, ProviderResponse):
            raise ProviderContractError("Provider returned an invalid response contract")
        if response.provider != selection.provider or response.model != selection.model:
            raise ProviderContractError(
                "Provider response identity does not match the selected model"
            )
        return response
