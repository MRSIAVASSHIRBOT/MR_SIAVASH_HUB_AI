from fastapi.testclient import TestClient

from client_helpers import authenticated_client
from mrhub.config import get_settings
from mrhub.main import create_app


def test_local_generation_is_disabled_by_default(tmp_path, monkeypatch):
    monkeypatch.setenv("MRH_DATABASE_PATH", str(tmp_path / "test.sqlite3"))
    monkeypatch.delenv("MRH_LOCAL_INFERENCE_ENABLED", raising=False)
    monkeypatch.delenv("MRH_LOCAL_INFERENCE_MODEL", raising=False)
    get_settings.cache_clear()
    client = authenticated_client()
    response = client.post("/models/generate", json={"input_text": "hello"})
    assert response.status_code == 503
    assert "disabled" in response.json()["detail"]
    get_settings.cache_clear()


def test_local_model_appears_only_when_explicitly_configured(tmp_path, monkeypatch):
    monkeypatch.setenv("MRH_DATABASE_PATH", str(tmp_path / "test.sqlite3"))
    monkeypatch.setenv("MRH_LOCAL_INFERENCE_ENABLED", "true")
    monkeypatch.setenv("MRH_LOCAL_INFERENCE_MODEL", "tiny-model")
    monkeypatch.setenv("MRH_LOCAL_INFERENCE_BASE_URL", "http://127.0.0.1:11434")
    get_settings.cache_clear()
    client = authenticated_client()
    response = client.get("/models")
    assert response.status_code == 200
    assert {item["provider"] for item in response.json()} == {"stub", "ollama"}
    get_settings.cache_clear()


def test_model_resource_assessment_endpoint_is_authenticated_and_read_only(tmp_path, monkeypatch):
    monkeypatch.setenv("MRH_DATABASE_PATH", str(tmp_path / "test.sqlite3"))
    get_settings.cache_clear()
    client = authenticated_client()
    response = client.post(
        "/models/assess",
        json={
            "hardware_report": {"memory": {"available_gib": 10}},
            "model_profile": {
                "name": "example-small",
                "minimum_ram_gib": 4,
                "recommended_ram_gib": 6,
                "requires_gpu": False,
            },
        },
    )
    assert response.status_code == 200
    assert response.json()["status"] == "likely_fit"
    assert response.json()["starts_inference"] is False
    get_settings.cache_clear()


def test_model_resource_assessment_returns_insufficient_data_when_gpu_is_required(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("MRH_DATABASE_PATH", str(tmp_path / "test.sqlite3"))
    get_settings.cache_clear()
    client = authenticated_client()
    response = client.post(
        "/models/assess",
        json={
            "hardware_report": {
                "memory": {"available_gib": 24},
                "gpu": {"status": "not_measured"},
            },
            "model_profile": {
                "name": "gpu-model",
                "minimum_ram_gib": 8,
                "recommended_ram_gib": 12,
                "requires_gpu": True,
            },
        },
    )
    assert response.status_code == 200
    assert response.json()["status"] == "insufficient_data"
    assert response.json()["starts_inference"] is False
    get_settings.cache_clear()


def test_model_profile_catalog_endpoint_is_authenticated_and_explicit(tmp_path, monkeypatch):
    monkeypatch.setenv("MRH_DATABASE_PATH", str(tmp_path / "test.sqlite3"))
    get_settings.cache_clear()
    client = authenticated_client()
    response = client.get("/models/profiles")
    assert response.status_code == 200
    assert len(response.json()) >= 2
    assert all(profile["verified"] is False for profile in response.json())
    get_settings.cache_clear()


def test_unknown_model_profile_returns_404(tmp_path, monkeypatch):
    monkeypatch.setenv("MRH_DATABASE_PATH", str(tmp_path / "test.sqlite3"))
    get_settings.cache_clear()
    client = authenticated_client()
    response = client.get("/models/profiles/not-a-real-profile")
    assert response.status_code == 404
    get_settings.cache_clear()


def test_model_profile_catalog_requires_authentication(tmp_path, monkeypatch):
    monkeypatch.setenv("MRH_DATABASE_PATH", str(tmp_path / "test.sqlite3"))
    get_settings.cache_clear()
    client = TestClient(create_app())
    response = client.get("/models/profiles")
    assert response.status_code in (401, 403)
    get_settings.cache_clear()


def test_compare_registered_models_is_read_only_and_preserves_unknown_gpu_data(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("MRH_DATABASE_PATH", str(tmp_path / "test.sqlite3"))
    get_settings.cache_clear()
    client = authenticated_client()
    response = client.post(
        "/models/compare",
        json={
            "hardware_report": {"memory": {"available_gib": 12}},
            "profile_ids": ["small-text-cpu-example", "gpu-model-example"],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 2
    assert body["starts_inference"] is False
    assert body["downloads_model"] is False
    assert body["results"][0]["assessment"]["status"] == "likely_fit"
    assert body["results"][1]["assessment"]["status"] == "insufficient_data"
    assert all(item["profile_verified"] is False for item in body["results"])
    get_settings.cache_clear()


def test_compare_registered_models_rejects_unknown_profile_ids(tmp_path, monkeypatch):
    monkeypatch.setenv("MRH_DATABASE_PATH", str(tmp_path / "test.sqlite3"))
    get_settings.cache_clear()
    client = authenticated_client()
    response = client.post(
        "/models/compare",
        json={
            "hardware_report": {"memory": {"available_gib": 12}},
            "profile_ids": ["small-text-cpu-example", "unknown-profile"],
        },
    )
    assert response.status_code == 404
    assert response.json()["detail"]["profile_ids"] == ["unknown-profile"]
    get_settings.cache_clear()


def test_compare_registered_models_requires_authentication(tmp_path, monkeypatch):
    monkeypatch.setenv("MRH_DATABASE_PATH", str(tmp_path / "test.sqlite3"))
    get_settings.cache_clear()
    client = TestClient(create_app())
    response = client.post(
        "/models/compare",
        json={
            "hardware_report": {"memory": {"available_gib": 12}},
            "profile_ids": ["small-text-cpu-example"],
        },
    )
    assert response.status_code in (401, 403)
    get_settings.cache_clear()



def test_model_recommendation_is_advisory_and_ranks_cpu_candidate(tmp_path, monkeypatch):
    monkeypatch.setenv("MRH_DATABASE_PATH", str(tmp_path / "test.sqlite3"))
    get_settings.cache_clear()
    client = authenticated_client()
    response = client.post(
        "/models/recommend",
        json={
            "hardware_report": {"memory": {"available_gib": 12}},
            "profile_ids": ["gpu-model-example", "small-text-cpu-example"],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["decision_mode"] == "advisory_only"
    assert body["starts_inference"] is False
    assert body["downloads_model"] is False
    assert body["selects_provider"] is False
    assert body["best_candidate_profile_id"] == "small-text-cpu-example"
    assert body["results"][0]["profile_id"] == "small-text-cpu-example"
    assert body["results"][0]["recommendation"] == "candidate"
    assert body["results"][1]["assessment"]["status"] == "insufficient_data"
    get_settings.cache_clear()


def test_model_recommendation_rejects_unknown_profiles(tmp_path, monkeypatch):
    monkeypatch.setenv("MRH_DATABASE_PATH", str(tmp_path / "test.sqlite3"))
    get_settings.cache_clear()
    client = authenticated_client()
    response = client.post(
        "/models/recommend",
        json={
            "hardware_report": {"memory": {"available_gib": 12}},
            "profile_ids": ["unknown-profile"],
        },
    )
    assert response.status_code == 404
    assert response.json()["detail"]["profile_ids"] == ["unknown-profile"]
    get_settings.cache_clear()


def test_model_recommendation_requires_authentication(tmp_path, monkeypatch):
    monkeypatch.setenv("MRH_DATABASE_PATH", str(tmp_path / "test.sqlite3"))
    get_settings.cache_clear()
    client = TestClient(create_app())
    response = client.post(
        "/models/recommend",
        json={
            "hardware_report": {"memory": {"available_gib": 12}},
            "profile_ids": ["small-text-cpu-example"],
        },
    )
    assert response.status_code in (401, 403)
    get_settings.cache_clear()



def test_model_select_is_capability_aware_and_only_uses_registered_provider(tmp_path, monkeypatch):
    monkeypatch.setenv("MRH_DATABASE_PATH", str(tmp_path / "test.sqlite3"))
    monkeypatch.delenv("MRH_LOCAL_INFERENCE_ENABLED", raising=False)
    monkeypatch.delenv("MRH_LOCAL_INFERENCE_MODEL", raising=False)
    get_settings.cache_clear()
    client = authenticated_client()
    response = client.post("/models/select", json={"requires_text": True, "prefer_local": True})
    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "stub"
    assert body["local"] is True
    unavailable = client.post("/models/select", json={"requires_vision": True})
    assert unavailable.status_code == 503
    get_settings.cache_clear()


def test_model_select_requires_authentication(tmp_path, monkeypatch):
    monkeypatch.setenv("MRH_DATABASE_PATH", str(tmp_path / "test.sqlite3"))
    get_settings.cache_clear()
    client = TestClient(create_app())
    response = client.post("/models/select", json={"requires_text": True})
    assert response.status_code in (401, 403)
    get_settings.cache_clear()


def test_provider_inventory_is_authenticated_and_does_not_probe_services(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("MRH_DATABASE_PATH", str(tmp_path / "test.sqlite3"))
    monkeypatch.setenv("MRH_LOCAL_INFERENCE_ENABLED", "true")
    monkeypatch.setenv("MRH_LOCAL_INFERENCE_MODEL", "tiny-model")
    get_settings.cache_clear()

    from mrhub.providers.ollama import OllamaProvider

    def unexpected_health_probe(self):
        raise AssertionError("inventory must not perform provider health probes")

    monkeypatch.setattr(OllamaProvider, "health", unexpected_health_probe)
    client = authenticated_client()
    response = client.get("/models/providers")

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 2
    assert body["health_probes_performed"] is False
    assert body["inference_started"] is False
    assert [item["provider"] for item in body["providers"]] == ["ollama", "stub"]
    assert all(item["registered"] is True for item in body["providers"])
    assert all(item["health_status"] == "not_checked" for item in body["providers"])
    assert "base_url" not in response.text
    assert "api_key" not in response.text
    get_settings.cache_clear()


def test_provider_inventory_requires_authentication(tmp_path, monkeypatch):
    monkeypatch.setenv("MRH_DATABASE_PATH", str(tmp_path / "test.sqlite3"))
    get_settings.cache_clear()
    client = TestClient(create_app())
    response = client.get("/models/providers")
    assert response.status_code in (401, 403)
    get_settings.cache_clear()


def test_provider_health_check_is_explicit_bounded_and_sanitized(tmp_path, monkeypatch):
    monkeypatch.setenv("MRH_DATABASE_PATH", str(tmp_path / "test.sqlite3"))
    monkeypatch.setenv("MRH_LOCAL_INFERENCE_ENABLED", "true")
    monkeypatch.setenv("MRH_LOCAL_INFERENCE_MODEL", "tiny-model")
    get_settings.cache_clear()

    from mrhub.providers.base import ProviderHealth
    from mrhub.providers.ollama import OllamaProvider

    observed_timeouts = []

    def fake_health(self, timeout_seconds=2.0):
        observed_timeouts.append(timeout_seconds)
        return ProviderHealth(available=False, reason_code="provider_unavailable")

    monkeypatch.setattr(OllamaProvider, "health", fake_health)
    client = authenticated_client()
    response = client.post(
        "/models/providers/health-check", json={"timeout_seconds": 1.5}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 2
    assert body["inference_started"] is False
    assert body["downloads_started"] is False
    assert observed_timeouts == [1.5]
    ollama = next(item for item in body["results"] if item["provider"] == "ollama")
    assert ollama["status"] == "unavailable"
    assert ollama["reason_code"] == "provider_unavailable"
    assert "private" not in response.text
    get_settings.cache_clear()


def test_provider_health_check_rejects_unbounded_timeout(tmp_path, monkeypatch):
    monkeypatch.setenv("MRH_DATABASE_PATH", str(tmp_path / "test.sqlite3"))
    get_settings.cache_clear()
    client = authenticated_client()
    response = client.post(
        "/models/providers/health-check", json={"timeout_seconds": 30}
    )
    assert response.status_code == 422
    get_settings.cache_clear()


def test_provider_health_check_requires_authentication(tmp_path, monkeypatch):
    monkeypatch.setenv("MRH_DATABASE_PATH", str(tmp_path / "test.sqlite3"))
    get_settings.cache_clear()
    client = TestClient(create_app())
    response = client.post("/models/providers/health-check", json={})
    assert response.status_code in (401, 403)
    get_settings.cache_clear()



def test_build_model_router_applies_agent_timeout_cap(monkeypatch):
    from pydantic import SecretStr

    from mrhub.api.routes import models
    from mrhub.config import Settings
    from mrhub.providers.base import ProviderHealth, ProviderRequest, ProviderResponse
    from mrhub.providers.types import ModelCapability, ModelDescriptor

    observed = {}

    class FakeProvider:
        def __init__(self, *, model, timeout_seconds, **kwargs):
            self.timeout_seconds = timeout_seconds
            provider_name = "ollama" if model == "local-model" else "openrouter"
            observed[provider_name] = timeout_seconds
            self.descriptor = ModelDescriptor(
                provider=provider_name,
                model=model,
                capability=ModelCapability(text=True),
                available=True,
                local=provider_name == "ollama",
                priority=1,
            )

        def health(self, timeout_seconds=2.0):
            return ProviderHealth(available=True, reason_code="test_ready")

        def generate(self, request: ProviderRequest):
            return ProviderResponse(
                provider=self.descriptor.provider,
                model=self.descriptor.model,
                output_text="{}",
            )

    monkeypatch.setattr(models, "OllamaProvider", FakeProvider)
    monkeypatch.setattr(models, "OpenRouterProvider", FakeProvider)
    monkeypatch.setattr(
        models,
        "get_settings",
        lambda: Settings(
            local_inference_enabled=True,
            local_inference_model="local-model",
            local_inference_timeout_seconds=300,
            remote_inference_enabled=True,
            remote_inference_api_key=SecretStr("test-key"),
            remote_inference_model="remote-model",
            remote_inference_timeout_seconds=120,
        ),
    )

    models.build_model_router(
        provider_mode="all",
        include_stub=False,
        max_timeout_seconds=30,
    )

    assert observed == {"ollama": 30, "openrouter": 30}
