from fastapi.testclient import TestClient

from client_helpers import authenticated_client
from mrhub.config import get_settings
from mrhub.main import create_app


def test_tool_catalog_is_authenticated_and_exposes_contracts():
    client = authenticated_client()
    response = client.get("/tools")
    assert response.status_code == 200
    catalog = response.json()
    assert [item["name"] for item in catalog] == ["text.echo"]
    assert catalog[0]["input_schema"]["properties"]["text"]["maxLength"] == 500
    assert catalog[0]["external_side_effect"] is False


def test_tool_invoke_executes_only_registered_safe_tool():
    client = authenticated_client()
    response = client.post("/tools/text.echo/invoke", json={"payload": {"text": "hello"}})
    assert response.status_code == 200
    assert response.json() == {
        "tool": "text.echo",
        "result": {"text": "hello", "character_count": 5},
        "executed": True,
    }


def test_tool_invoke_rejects_unregistered_tool():
    client = authenticated_client()
    response = client.post(
        "/tools/shell.execute/invoke",
        json={"payload": {"command": "echo not executed"}},
    )
    assert response.status_code == 404


def test_tool_invoke_validates_payload_without_echoing_input():
    client = authenticated_client()
    response = client.post("/tools/text.echo/invoke", json={"payload": {"text": ""}})
    assert response.status_code == 422
    assert response.json()["detail"] == "Tool input validation failed"
    assert "text" not in response.text


def test_tool_catalog_requires_authentication(tmp_path, monkeypatch):
    monkeypatch.setenv("MRH_DATABASE_PATH", str(tmp_path / "test.sqlite3"))
    get_settings.cache_clear()
    response = TestClient(create_app()).get("/tools")
    assert response.status_code in (401, 403)
    get_settings.cache_clear()


def test_tool_invoke_requires_authentication(tmp_path, monkeypatch):
    monkeypatch.setenv("MRH_DATABASE_PATH", str(tmp_path / "test.sqlite3"))
    get_settings.cache_clear()
    response = TestClient(create_app()).post(
        "/tools/text.echo/invoke", json={"payload": {"text": "hello"}}
    )
    assert response.status_code in (401, 403)
    get_settings.cache_clear()
