"""Deterministic development adapter; this is not an AI model or inference engine."""

from mrhub.providers.base import ProviderHealth, ProviderRequest, ProviderResponse
from mrhub.providers.router import ModelCapability, ModelDescriptor


class StubProvider:
    descriptor = ModelDescriptor(
        provider="stub",
        model="stub-text-v1",
        capability=ModelCapability(text=True),
        available=True,
        local=True,
        priority=1000,
    )

    def generate(self, request: ProviderRequest) -> ProviderResponse:
        return ProviderResponse(
            provider=self.descriptor.provider,
            model=self.descriptor.model,
            output_text=f"[STUB ONLY] Received {len(request.input_text)} characters. No model inference was performed.",
            finish_reason="stub",
        )

    def health(self, timeout_seconds: float = 2.0) -> ProviderHealth:
        return ProviderHealth(available=True, reason_code="stub_ready")
