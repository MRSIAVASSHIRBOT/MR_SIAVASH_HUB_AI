from fastapi.testclient import TestClient

from mrhub.main import create_app


def authenticated_client() -> TestClient:
    client = TestClient(create_app())
    setup = client.post(
        "/auth/setup",
        json={"password": "test-only-strong-password-2026"},
    )
    assert setup.status_code == 201
    login = client.post(
        "/auth/login",
        json={"username": "owner", "password": "test-only-strong-password-2026"},
    )
    assert login.status_code == 200
    client.headers.update(
        {"Authorization": f"Bearer {login.json()['access_token']}"}
    )
    return client
