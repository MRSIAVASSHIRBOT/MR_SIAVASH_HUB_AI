import pytest

from mrhub.providers.base import (
    ProviderContractError,
    ProviderHealth,
    ProviderRequest,
)
from mrhub.providers.ollama import OllamaProvider
from mrhub.providers.openrouter import OpenRouterProvider
from mrhub.providers.registry import ProviderRegistry
from mrhub.providers.router import ModelCapability, ModelDescriptor, ModelRequest, ModelRouter
from mrhub.providers.stub import StubProvider
from mrhub.providers.vision import OllamaVisionProvider


def test_stub_provider_is_explicit_and_does_not_claim_inference():
    response = StubProvider().generate(ProviderRequest(input_text="hello"))
    assert response.provider == "stub"
    assert response.finish_reason == "stub"
    assert "No model inference was performed" in response.output_text


def test_registry_rejects_duplicate_provider_model():
    registry = ProviderRegistry()
    provider = StubProvider()
    registry.register(provider)
    try:
        registry.register(provider)
    except ValueError as exc:
        assert "already registered" in str(exc)
    else:
        raise AssertionError("duplicate registration must fail")


def test_router_dispatches_only_to_registered_adapter():
    router = ModelRouter()
    router.register_provider(StubProvider())
    response = router.generate(ModelRequest(prefer_local=True), ProviderRequest(input_text="test"))
    assert response.provider == "stub"


def test_router_hydrates_capabilities_from_a_prepopulated_registry():
    registry = ProviderRegistry()
    provider = StubProvider()
    registry.register(provider)

    router = ModelRouter(registry=registry)

    assert router.catalog() == [provider.descriptor]
    response = router.generate(
        ModelRequest(prefer_local=True),
        ProviderRequest(input_text="injected registry"),
    )
    assert response.provider == provider.descriptor.provider
    assert response.model == provider.descriptor.model


def test_router_preserves_an_injected_falsey_provider_registry():
    class FalseyProviderRegistry(ProviderRegistry):
        def __bool__(self):
            return False

    registry = FalseyProviderRegistry()
    router = ModelRouter(registry=registry)
    provider = StubProvider()

    assert router.registry is registry
    router.register_provider(provider)
    assert registry.get(provider.descriptor.provider, provider.descriptor.model) is provider


@pytest.mark.parametrize(
    "health",
    [
        None,
        object(),
        type("HealthLike", (), {"available": True, "reason_code": "ready"})(),
        ProviderHealth(available=1, reason_code="ready"),
        ProviderHealth(available=True, reason_code=""),
    ],
)
def test_router_rejects_invalid_provider_health_contract(health):
    class InvalidHealthProvider:
        descriptor = StubProvider.descriptor

        def health(self, timeout_seconds=2.0):
            return health

        def generate(self, request):
            raise AssertionError("generation must not start after an invalid health response")

    router = ModelRouter()
    router.register_provider(InvalidHealthProvider())

    with pytest.raises(ProviderContractError, match="invalid health contract"):
        router.generate(ModelRequest(prefer_local=True), ProviderRequest(input_text="test"))


def test_router_does_not_fallback_when_local_adapter_is_missing():
    router = ModelRouter()
    router.register(
        ModelDescriptor(
            provider="cloud",
            model="cloud-text",
            capability=ModelCapability(text=True),
            local=False,
        )
    )
    try:
        router.generate(ModelRequest(prefer_local=True), ProviderRequest(input_text="test"))
    except LookupError as exc:
        assert "No available model" in str(exc)
    else:
        raise AssertionError("local-only request must not fall back")


def test_registry_missing_adapter_fails_closed():
    registry = ProviderRegistry()
    try:
        registry.get("unknown", "model")
    except LookupError as exc:
        assert "No provider adapter" in str(exc)
    else:
        raise AssertionError("missing adapters must fail closed")


def test_router_rejects_duplicate_descriptor_without_overwriting_existing_entry():
    router = ModelRouter()
    original = ModelDescriptor(
        provider="local",
        model="small-model",
        capability=ModelCapability(text=True),
        local=True,
        priority=20,
    )
    replacement = ModelDescriptor(
        provider="local",
        model="small-model",
        capability=ModelCapability(text=True, vision=True),
        local=True,
        priority=1,
    )
    router.register(original)

    try:
        router.register(replacement)
    except ValueError as exc:
        assert "already registered" in str(exc)
    else:
        raise AssertionError("duplicate descriptor must fail")

    assert router.catalog() == [original]
    assert router.catalog()[0].capability.vision is False
    assert router.catalog()[0].priority == 20


def test_router_duplicate_descriptor_does_not_partially_register_provider_adapter():
    router = ModelRouter()
    provider = StubProvider()
    router.register(provider.descriptor)

    try:
        router.register_provider(provider)
    except ValueError as exc:
        assert "already registered" in str(exc)
    else:
        raise AssertionError("duplicate descriptor must fail before adapter registration")

    try:
        router.registry.get(provider.descriptor.provider, provider.descriptor.model)
    except LookupError as exc:
        assert "No provider adapter" in str(exc)
    else:
        raise AssertionError("adapter registry must remain unchanged after rejection")


def test_provider_transport_parameter_is_preserved_and_accessible():
    """Provider transport parameter should be preserved and accessible."""
    import httpx

    class CustomMockTransport(httpx.BaseTransport):
        def handle_request(self, request):
            raise NotImplementedError("Mock transport for testing only")

    from mrhub.providers.openrouter import OpenRouterProvider

    custom_transport = CustomMockTransport()
    provider = OpenRouterProvider(
        model="gpt-4o",
        api_key="test-key",
        transport=custom_transport,
    )

    assert provider._transport is custom_transport
    assert hasattr(provider, "_async_transport")
    assert provider._async_transport is custom_transport


@pytest.mark.parametrize(
    "provider_class", [OllamaProvider, OllamaVisionProvider, OpenRouterProvider]
)
def test_provider_transport_parameter_accepted_and_preserved(provider_class):
    """All provider classes should accept and preserve transport parameter."""
    import httpx

    class CustomMockTransport(httpx.BaseTransport):
        def handle_request(self, request):
            raise NotImplementedError("Mock transport for testing only")

    mock_transport = CustomMockTransport()

    if provider_class is OllamaProvider:
        provider = provider_class(
            model="test-model",
            transport=mock_transport,
        )
    elif provider_class is OllamaVisionProvider:
        provider = provider_class(
            model="test-vision-model",
            transport=mock_transport,
        )
    elif provider_class is OpenRouterProvider:
        provider = provider_class(
            model="gpt-4o",
            api_key="test-key",
            transport=mock_transport,
        )

    assert provider._transport is mock_transport


def test_openrouter_provider_transport_preserved_with_default_none():
    """OpenRouter provider should default transport to None."""
    from mrhub.providers.openrouter import OpenRouterProvider

    provider = OpenRouterProvider(model="gpt-4o", api_key="test-key")
    assert provider._transport is None
    assert hasattr(provider, "_async_transport")
    assert provider._async_transport is None


def test_router_does_not_generate_when_provider_health_is_unavailable():
    class UnavailableProvider:
        descriptor = StubProvider.descriptor

        def health(self, timeout_seconds=2.0):
            assert timeout_seconds == 2.0
            return ProviderHealth(available=False, reason_code="offline")

        def generate(self, request):
            raise AssertionError("generation must not start for an unavailable provider")

    router = ModelRouter()
    router.register_provider(UnavailableProvider())

    with pytest.raises(LookupError, match="Selected provider is unavailable"):
        router.generate(ModelRequest(prefer_local=True), ProviderRequest(input_text="test"))


def test_router_rejects_non_provider_response_values():
    class InvalidProvider:
        descriptor = StubProvider.descriptor

        def health(self, timeout_seconds=2.0):
            return ProviderHealth(available=True, reason_code="ready")

        def generate(self, request):
            return {"provider": "stub", "model": "stub-text-v1", "output_text": "invalid"}

    router = ModelRouter()
    router.register_provider(InvalidProvider())

    with pytest.raises(ProviderContractError, match="invalid response contract"):
        router.generate(ModelRequest(prefer_local=True), ProviderRequest(input_text="test"))
