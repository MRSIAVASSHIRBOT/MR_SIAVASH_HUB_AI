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
