from mrhub.providers.base import ProviderRequest, ProviderUnavailableError
from mrhub.providers.registry import ProviderRegistry
from mrhub.providers.router import ModelCapability, ModelDescriptor, ModelRequest, ModelRouter
from mrhub.providers.stub import StubProvider


def test_stub_provider_is_explicit_and_does_not_claim_inference():
    provider = StubProvider()
    response = provider.generate(ProviderRequest(input_text="hello"))
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
    provider = StubProvider()
    router.register_provider(provider)
    response = router.generate(ModelRequest(prefer_local=True), ProviderRequest(input_text="test"))
    assert response.provider == "stub"


def test_router_does_not_fallback_when_local_adapter_is_missing():
    router = ModelRouter()
    router.register(ModelDescriptor(
        provider="cloud", model="cloud-text",
        capability=ModelCapability(text=True), local=False,
    ))
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
