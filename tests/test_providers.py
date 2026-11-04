import pytest

from mrhub.providers.base import (
    ProviderContractError,
    ProviderHealth,
    ProviderRequest,
    ProviderResponse,
)
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


@pytest.mark.parametrize(
    ("provider_name", "model_name"),
    [
        ("unexpected-provider", "stub-text-v1"),
        ("stub", "unexpected-model"),
    ],
)
def test_router_rejects_response_with_mismatched_provider_identity(provider_name, model_name):
    class MismatchedProvider:
        descriptor = StubProvider.descriptor

        def health(self, timeout_seconds=2.0):
            return ProviderHealth(available=True, reason_code="ready")

        def generate(self, request):
            return ProviderResponse(
                provider=provider_name,
                model=model_name,
                output_text="response must not pass the router",
            )

    router = ModelRouter()
    router.register_provider(MismatchedProvider())

    with pytest.raises(ProviderContractError) as error:
        router.generate(ModelRequest(prefer_local=True), ProviderRequest(input_text="test"))

    assert error.value.code == "provider_contract_violation"
    assert "response must not pass" not in str(error.value)


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
