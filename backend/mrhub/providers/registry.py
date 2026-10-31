"""Explicit provider registry with duplicate protection."""

from mrhub.providers.base import ModelProvider


class ProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[tuple[str, str], ModelProvider] = {}

    def register(self, provider: ModelProvider) -> None:
        descriptor = provider.descriptor
        key = (descriptor.provider, descriptor.model)
        if key in self._providers:
            raise ValueError("Provider model is already registered")
        self._providers[key] = provider

    def get(self, provider: str, model: str) -> ModelProvider:
        try:
            return self._providers[(provider, model)]
        except KeyError as exc:
            raise LookupError("No provider adapter is registered for this model") from exc

    def catalog(self):
        return [provider.descriptor for provider in self._providers.values()]
