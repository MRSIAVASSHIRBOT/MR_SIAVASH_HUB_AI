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
