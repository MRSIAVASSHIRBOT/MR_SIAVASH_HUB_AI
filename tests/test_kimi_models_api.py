import sqlite3

import httpx
import pytest

from client_helpers import authenticated_client
from mrhub.api.routes import models as model_routes
from mrhub.config import get_settings
from mrhub.infrastructure.request_limits import KimiRequestRateLimitRepository
from mrhub.providers.kimi import KimiProvider
from mrhub.providers.router import ModelRouter


def _set_kimi_config(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("MRH_DATABASE_PATH", str(tmp_path / "kimi-model.sqlite3"))
    monkeypatch.setenv("MRH_KIMI_INFERENCE_ENABLED", "true")
    monkeypatch.setenv("MRH_KIMI_API_KEY", "test-key")
    monkeypatch.setenv("MRH_KIMI_MODEL", "kimi-k3.1-pro")
    monkeypatch.setenv("MRH_KIMI_REASONING_EFFORT", "high")
    get_settings.cache_clear()
    model_routes._KIMI_REQUEST_LIMITER = None


def test_kimi_generation_is_disabled_by_default(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("MRH_DATABASE_PATH", str(tmp_path / "kimi-disabled.sqlite3"))
    monkeypatch.setenv("MRH_KIMI_INFERENCE_ENABLED", "false")
    monkeypatch.delenv("MRH_KIMI_API_KEY", raising=False)
    get_settings.cache_clear()

    response = authenticated_client().post(
        "/models/generate-kimi",
        json={"input_text": "hello"},
    )
    assert response.status_code == 503
    assert "no Kimi request was made" in response.json()["detail"]
    get_settings.cache_clear()


def test_kimi_provider_is_listed_only_when_explicitly_configured(
    tmp_path, monkeypatch
) -> None:
    _set_kimi_config(monkeypatch, tmp_path)
    response = authenticated_client().get("/models/providers")
    assert response.status_code == 200
    kimi = [item for item in response.json()["providers"] if item["provider"] == "moonshot"]
    assert len(kimi) == 1
    assert kimi[0]["model"] == "kimi-k3.1-pro"
    assert kimi[0]["local"] is False
    assert kimi[0]["health_status"] == "not_checked"
    get_settings.cache_clear()


def test_kimi_generation_uses_only_the_explicit_kimi_provider(
    tmp_path, monkeypatch
) -> None:
    _set_kimi_config(monkeypatch, tmp_path)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": "Kimi test answer"}, "finish_reason": "stop"}
                ],
                "usage": {"prompt_tokens": 2, "completion_tokens": 3},
            },
        )

    def build_router(*, provider_mode="all", include_stub=True, max_timeout_seconds=None):
        assert provider_mode == "kimi"
        assert include_stub is False
        router = ModelRouter()
        router.register_provider(
            KimiProvider(
                model="kimi-k3.1-pro",
                api_key="test-key",
                transport=httpx.MockTransport(handler),
            )
        )
        return router

    monkeypatch.setattr(model_routes, "build_model_router", build_router)
    client = authenticated_client()
    # authenticated_client assigns its own isolated database path; bind the
    # per-test quota to that final path, not the pre-client settings path.
    model_routes._KIMI_REQUEST_LIMITER = KimiRequestRateLimitRepository(
        get_settings().database_path, max_requests=1, window_seconds=60
    )
    extra_field = client.post(
        "/models/generate-kimi",
        json={"input_text": "hello", "unexpected": "must be rejected"},
    )
    assert extra_field.status_code == 422

    boolean_limit = client.post(
        "/models/generate-kimi",
        json={"input_text": "hello", "max_output_tokens": True},
    )
    assert boolean_limit.status_code == 422

    response = client.post(
        "/models/generate-kimi",
        json={"input_text": "hello", "max_output_tokens": 32},
    )
    assert response.status_code == 200
    assert response.json()["provider"] == "moonshot"
    assert response.json()["output_text"] == "Kimi test answer"

    limited = client.post(
        "/models/generate-kimi",
        json={"input_text": "second request", "max_output_tokens": 32},
    )
    assert limited.status_code == 429
    assert limited.json()["detail"]["code"] == "kimi_rate_limited"
    assert int(limited.headers["Retry-After"]) >= 1
    get_settings.cache_clear()



def test_kimi_vision_endpoint_uses_explicit_provider_and_inline_image(
    tmp_path, monkeypatch
) -> None:
    import base64

    _set_kimi_config(monkeypatch, tmp_path)
    image = b"\x89PNG\r\n\x1a\n" + b"test-image"
    image_data_url = "data:image/png;base64," + base64.b64encode(image).decode()

    provider_requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        provider_requests.append((request.method, request.url.path))
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "Vision result"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 20, "completion_tokens": 5},
            },
        )

    def build_router(*, provider_mode="all", include_stub=True, max_timeout_seconds=None):
        assert provider_mode == "kimi"
        assert include_stub is False
        router = ModelRouter()
        router.register_provider(
            KimiProvider(
                model="kimi-k3.1-pro",
                api_key="test-key",
                transport=httpx.MockTransport(handler),
            )
        )
        return router

    monkeypatch.setattr(model_routes, "build_model_router", build_router)
    client = authenticated_client()
    # Bind the test quota after the helper finalizes its isolated DB path.
    model_routes._KIMI_REQUEST_LIMITER = KimiRequestRateLimitRepository(
        get_settings().database_path, max_requests=1, window_seconds=60
    )
    invalid_limit = client.post(
        "/models/generate-kimi-vision",
        json={
            "prompt": "Describe it",
            "image_data_url": image_data_url,
            "max_output_tokens": True,
        },
    )
    assert invalid_limit.status_code == 422

    response = client.post(
        "/models/generate-kimi-vision",
        json={"prompt": "Describe it", "image_data_url": image_data_url},
    )
    assert response.status_code == 200
    assert response.json()["provider"] == "moonshot"
    assert response.json()["output_text"] == "Vision result"
    # The generation path makes one bounded POST, not a redundant preflight GET.
    assert provider_requests == [("POST", "/v1/chat/completions")]

    # Text and Vision share one durable owner quota.
    limited = client.post(
        "/models/generate-kimi",
        json={"input_text": "quota is shared across Kimi endpoints"},
    )
    assert limited.status_code == 429
    assert limited.json()["detail"]["code"] == "kimi_rate_limited"
    get_settings.cache_clear()

def test_remote_mode_never_selects_kimi_when_both_cloud_providers_are_enabled(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("MRH_DATABASE_PATH", str(tmp_path / "both-providers.sqlite3"))
    monkeypatch.setenv("MRH_REMOTE_INFERENCE_ENABLED", "true")
    monkeypatch.setenv("MRH_REMOTE_INFERENCE_API_KEY", "openrouter-test-key")
    monkeypatch.setenv("MRH_REMOTE_INFERENCE_MODEL", "example/free-model")
    monkeypatch.setenv("MRH_KIMI_INFERENCE_ENABLED", "true")
    monkeypatch.setenv("MRH_KIMI_API_KEY", "kimi-test-key")
    monkeypatch.setenv("MRH_KIMI_MODEL", "kimi-k3.1-pro")
    get_settings.cache_clear()

    remote_router = model_routes.build_model_router(
        provider_mode="remote",
        include_stub=False,
    )
    assert [item.provider for item in remote_router.catalog()] == ["openrouter"]

    kimi_router = model_routes.build_model_router(
        provider_mode="kimi",
        include_stub=False,
    )
    assert [item.provider for item in kimi_router.catalog()] == ["moonshot"]
    get_settings.cache_clear()


def test_kimi_owner_limiter_is_atomic_across_instances_and_expires_old_events(
    tmp_path,
) -> None:
    from concurrent.futures import ThreadPoolExecutor

    database_path = tmp_path / "shared-kimi-limits.sqlite3"
    limiters = [
        KimiRequestRateLimitRepository(
            database_path, max_requests=3, window_seconds=60
        )
        for _ in range(2)
    ]
    with ThreadPoolExecutor(max_workers=12) as pool:
        results = list(
            pool.map(
                lambda index: limiters[index % 2].consume("owner-a"),
                range(24),
            )
        )
    assert sum(result is None for result in results) == 3
    assert all(result is None or result >= 1 for result in results)

    # Simulate expiry without sleeping; a second limiter instance sees the same DB.
    connection = sqlite3.connect(database_path)
    try:
        connection.execute(
            "UPDATE kimi_request_events SET requested_at = ? WHERE owner_user_id = ?",
            ("2000-01-01T00:00:00+00:00", "owner-a"),
        )
        connection.commit()
    finally:
        connection.close()
    assert limiters[1].consume("owner-a") is None
    assert limiters[0].consume("owner-b") is None


def test_kimi_rate_limit_repository_rejects_invalid_bounds(tmp_path) -> None:
    for invalid in (True, 0, -1, 1.5):
        with pytest.raises(ValueError, match="positive integers"):
            KimiRequestRateLimitRepository(
                tmp_path / "invalid-limit.sqlite3",
                max_requests=invalid,
            )
