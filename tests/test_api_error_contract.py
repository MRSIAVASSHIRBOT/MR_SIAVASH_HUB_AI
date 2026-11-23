from fastapi import HTTPException
from fastapi.testclient import TestClient

from client_helpers import authenticated_client
from mrhub.main import create_app


def test_validation_error_has_correlation_contract_without_echoing_input():
    client = authenticated_client()
    sentinel = "ghp_abcdefghijklmnopqrstuvwx123456"
    response = client.post(
        "/tools/text.echo/invoke",
        json={
            "payload": {"text": "safe"},
            "private_extra_field": sentinel,
        },
    )

    assert response.status_code == 422
    body = response.json()
    assert body["detail"]
    assert "input" not in body["detail"][0]
    assert "ctx" not in body["detail"][0]
    assert sentinel not in str(body)
    assert body["error"]["code"] == "request_validation_error"
    assert body["error"]["request_id"] == response.headers["X-Request-ID"]
    assert body["error"]["issues"][0]["message"] == "Invalid request value"


def test_http_exception_keeps_legacy_detail_and_adds_stable_error_code():
    app = create_app()

    def conflict():
        raise HTTPException(status_code=409, detail={"reason": "stale_revision"})

    app.add_api_route("/_test/conflict", conflict, methods=["GET"])
    response = TestClient(app).get("/_test/conflict")

    assert response.status_code == 409
    assert response.json()["detail"] == {"reason": "stale_revision"}
    assert response.json()["error"]["code"] == "state_conflict"
    assert response.json()["error"]["request_id"] == response.headers["X-Request-ID"]


def test_unhandled_exception_never_exposes_exception_text():
    app = create_app()
    private_detail = "api_key=not-a-real-secret-must-not-be-returned"

    def fail():
        raise RuntimeError(private_detail)

    app.add_api_route("/_test/fail", fail, methods=["GET"])
    response = TestClient(app, raise_server_exceptions=False).get("/_test/fail")

    assert response.status_code == 500
    body = response.json()
    assert body["detail"] == "Internal server error"
    assert body["error"]["code"] == "internal_error"
    assert private_detail not in response.text
    assert body["error"]["request_id"] == response.headers["X-Request-ID"]
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Cache-Control"] == "no-store"
