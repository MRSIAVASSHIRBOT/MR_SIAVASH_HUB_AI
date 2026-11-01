import os
import tempfile
from pathlib import Path
from uuid import uuid4

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from mrhub.config import get_settings
from mrhub.main import create_app


def authenticated_client() -> TestClient:
    database_path = Path(tempfile.gettempdir()) / f"mrhub-test-{uuid4().hex}.sqlite3"
    os.environ["MRH_DATABASE_PATH"] = str(database_path)
    os.environ["MRH_WORKFLOW_INPUT_ENCRYPTION_KEY"] = Fernet.generate_key().decode("ascii")
    get_settings.cache_clear()
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
