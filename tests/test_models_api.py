from client_helpers import authenticated_client
from mrhub.config import get_settings


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
