from mrhub.providers.base import ProviderRequest
from mrhub.providers.registry import ProviderRegistry
from mrhub.providers.router import ModelCapability, ModelDescriptor, ModelRequest, ModelRouter
from mrhub.providers.stub import StubProvider


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
