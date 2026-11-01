from fastapi.testclient import TestClient

from mrhub.config import get_settings
from mrhub.main import create_app


def test_protected_route_rejects_missing_session(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("MRH_DATABASE_PATH", str(tmp_path / "missing.sqlite3"))
    get_settings.cache_clear()
    client = TestClient(create_app())
    response = client.get("/tasks")
    assert response.status_code == 401


def test_owner_setup_login_logout_and_revocation(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("MRH_DATABASE_PATH", str(tmp_path / "auth.sqlite3"))
    get_settings.cache_clear()
    client = TestClient(create_app())
    password = "test-only-strong-password-2026"

    setup = client.post("/auth/setup", json={"password": password})
    assert setup.status_code == 201
    duplicate_setup = client.post("/auth/setup", json={"password": password})
    assert duplicate_setup.status_code == 409

    login = client.post(
        "/auth/login",
        json={"username": "owner", "password": password},
    )
    assert login.status_code == 200
    token = login.json()["access_token"]
    assert len(token) >= 40

    client.headers.update({"Authorization": f"Bearer {token}"})
    assert client.get("/tasks").status_code == 200
    assert client.post("/auth/logout").status_code == 204
    assert client.get("/tasks").status_code == 401


def test_setup_rejects_short_password(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("MRH_DATABASE_PATH", str(tmp_path / "short.sqlite3"))
    get_settings.cache_clear()
    client = TestClient(create_app())
    response = client.post("/auth/setup", json={"password": "short"})
    assert response.status_code == 422


def test_invalid_password_does_not_create_session(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("MRH_DATABASE_PATH", str(tmp_path / "invalid-login.sqlite3"))
    get_settings.cache_clear()
    client = TestClient(create_app())
    setup = client.post(
        "/auth/setup",
        json={"password": "test-only-strong-password-2026"},
    )
    assert setup.status_code == 201
    failed = client.post(
        "/auth/login",
        json={"username": "owner", "password": "incorrect-password"},
    )
    assert failed.status_code == 401
    assert client.get("/tasks").status_code == 401



def test_login_throttles_repeated_failures_and_success_resets_limit(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("MRH_DATABASE_PATH", str(tmp_path / "login-limit.sqlite3"))
    get_settings.cache_clear()
    client = TestClient(create_app())
    password = "test-only-strong-password-2026"
    assert client.post("/auth/setup", json={"password": password}).status_code == 201

    for _ in range(2):
        failed = client.post(
            "/auth/login",
            json={"username": "owner", "password": "incorrect-password"},
        )
        assert failed.status_code == 401
        assert failed.headers["Cache-Control"] == "no-store"

    successful = client.post(
        "/auth/login",
        json={"username": "owner", "password": password},
    )
    assert successful.status_code == 200

    for _ in range(5):
        failed = client.post(
            "/auth/login",
            json={"username": "owner", "password": "incorrect-password"},
        )
        assert failed.status_code == 401

    limited = client.post(
        "/auth/login",
        json={"username": "owner", "password": password},
    )
    assert limited.status_code == 429
    assert limited.headers["Cache-Control"] == "no-store"
    assert limited.headers["Pragma"] == "no-cache"
    assert 1 <= int(limited.headers["Retry-After"]) <= 300



def test_owner_setup_rejects_non_loopback_client(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("MRH_DATABASE_PATH", str(tmp_path / "remote-setup.sqlite3"))
    get_settings.cache_clear()
    client = TestClient(create_app(), client=("203.0.113.10", 43120))
    response = client.post(
        "/auth/setup",
        json={"password": "test-only-strong-password-2026"},
        headers={"X-Forwarded-For": "127.0.0.1"},
    )
    assert response.status_code == 403


def test_login_response_is_not_cacheable(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("MRH_DATABASE_PATH", str(tmp_path / "no-cache.sqlite3"))
    get_settings.cache_clear()
    client = TestClient(create_app())
    password = "test-only-strong-password-2026"
    assert client.post("/auth/setup", json={"password": password}).status_code == 201

    response = client.post(
        "/auth/login",
        json={"username": "owner", "password": password},
    )
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["Pragma"] == "no-cache"
