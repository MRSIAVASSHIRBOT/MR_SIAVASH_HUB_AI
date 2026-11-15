from uuid import UUID

from fastapi.testclient import TestClient

from mrhub.main import create_app


def test_valid_request_id_is_echoed_and_logged_with_route_template(caplog):
    request_id = "12345678-1234-4234-8234-123456789abc"
    client = TestClient(create_app())

    with caplog.at_level("INFO", logger="mrhub.request"):
        response = client.get(
            "/health?private_query=must-not-be-logged",
            headers={"X-Request-ID": request_id},
        )

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == request_id
    assert request_id in caplog.text
    assert "/health" in caplog.text
    assert "private_query" not in caplog.text
    assert "must-not-be-logged" not in caplog.text


def test_missing_request_id_is_generated_and_returned():
    response = TestClient(create_app()).get("/health")

    generated = response.headers["X-Request-ID"]
    assert str(UUID(generated)) == generated


def test_malformed_or_oversized_request_id_is_replaced():
    for invalid in ("not-a-uuid", "x" * 4096):
        response = TestClient(create_app()).get(
            "/health",
            headers={"X-Request-ID": invalid},
        )

        generated = response.headers["X-Request-ID"]
        assert str(UUID(generated)) == generated
        assert generated != invalid
