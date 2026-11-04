import httpx

from client_helpers import authenticated_client
from mrhub.api.routes import models as model_routes
from mrhub.config import get_settings
from mrhub.providers.openrouter import OpenRouterProvider
from mrhub.providers.router import ModelRouter


def _set_remote_config(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("MRH_DATABASE_PATH", str(tmp_path / "remote-model.sqlite3"))
    monkeypatch.setenv("MRH_REMOTE_INFERENCE_ENABLED", "true")
    monkeypatch.setenv("MRH_REMOTE_INFERENCE_API_KEY", "test-key")
    monkeypatch.setenv("MRH_REMOTE_INFERENCE_MODEL", "example/free-model")
    monkeypatch.setenv("MRH_REMOTE_INFERENCE_BASE_URL", "https://openrouter.ai/api/v1")
    get_settings.cache_clear()


def test_remote_generation_is_disabled_by_default_and_does_not_call_cloud(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("MRH_DATABASE_PATH", str(tmp_path / "disabled-remote.sqlite3"))
    monkeypatch.setenv("MRH_REMOTE_INFERENCE_ENABLED", "false")
    monkeypatch.delenv("MRH_REMOTE_INFERENCE_API_KEY", raising=False)
    monkeypatch.delenv("MRH_REMOTE_INFERENCE_MODEL", raising=False)
    get_settings.cache_clear()
    client = authenticated_client()
    response = client.post("/models/generate-remote", json={"input_text": "hello"})
    assert response.status_code == 503
    assert "no cloud request was made" in response.json()["detail"]
    get_settings.cache_clear()


def test_remote_provider_is_catalogued_only_when_explicitly_configured(
    tmp_path, monkeypatch
) -> None:
    _set_remote_config(monkeypatch, tmp_path)
    client = authenticated_client()
    response = client.get("/models/providers")
    assert response.status_code == 200
    remote = [item for item in response.json()["providers"] if item["provider"] == "openrouter"]
    assert len(remote) == 1
    assert remote[0]["model"] == "example/free-model"
    assert remote[0]["local"] is False
    assert remote[0]["health_status"] == "not_checked"
    assert response.json()["health_probes_performed"] is False
    assert response.json()["inference_started"] is False
    get_settings.cache_clear()


def test_remote_generation_uses_configured_provider_explicitly(
    tmp_path, monkeypatch
) -> None:
    _set_remote_config(monkeypatch, tmp_path)
    client = authenticated_client()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "explicit remote answer"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 3, "completion_tokens": 4},
            },
        )

    def build_router(*, provider_mode="all", include_stub=True) -> ModelRouter:
        assert provider_mode == "remote"
        assert include_stub is False
        router = ModelRouter()
        router.register_provider(
            OpenRouterProvider(
                model="example/free-model",
                api_key="test-key",
                transport=httpx.MockTransport(handler),
            )
        )
        return router

    monkeypatch.setattr(model_routes, "build_model_router", build_router)
    response = client.post(
        "/models/generate-remote",
        json={"input_text": "hello", "max_output_tokens": 64},
    )
    assert response.status_code == 200
    assert response.json()["provider"] == "openrouter"
    assert response.json()["output_text"] == "explicit remote answer"
    assert response.json()["output_tokens"] == 4
    get_settings.cache_clear()


def test_remote_failure_returns_sanitized_error_without_local_fallback(
    tmp_path, monkeypatch
) -> None:
    _set_remote_config(monkeypatch, tmp_path)
    client = authenticated_client()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, json={"data": []})
        return httpx.Response(503, text="provider internals and secret details")

    def build_router(*, provider_mode="all", include_stub=True) -> ModelRouter:
        assert provider_mode == "remote"
        assert include_stub is False
        router = ModelRouter()
        router.register_provider(
            OpenRouterProvider(
                model="example/free-model",
                api_key="test-key",
                transport=httpx.MockTransport(handler),
            )
        )
        return router

    monkeypatch.setattr(model_routes, "build_model_router", build_router)
    response = client.post("/models/generate-remote", json={"input_text": "hello"})
    assert response.status_code == 503
    assert response.json()["detail"] == "provider_unavailable"
    assert "provider internals" not in response.text
    get_settings.cache_clear()
