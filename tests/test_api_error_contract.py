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

    # Unknown JSON keys can themselves contain credentials. They must not be
    # reflected in the Pydantic location path.
    secret_key = "ghp_abcdefghijklmnopqrstuvwx123456"
    key_response = client.post(
        "/tools/text.echo/invoke",
        json={"payload": {"text": "safe"}, secret_key: "untrusted"},
    )
    assert key_response.status_code == 422
    assert secret_key not in key_response.text
    assert "abcdefghijklmnopqrstuvwx" not in key_response.text


def test_http_exception_preserves_only_reviewed_legacy_detail_shapes():
    app = create_app()

    def conflict():
        raise HTTPException(status_code=409, detail={"reason": "stale_revision"})

    def not_found():
        raise HTTPException(status_code=404, detail="Task not found")

    app.add_api_route("/_test/conflict", conflict, methods=["GET"])
    app.add_api_route("/_test/not-found", not_found, methods=["GET"])
    client = TestClient(app)

    conflict_response = client.get("/_test/conflict")
    assert conflict_response.status_code == 409
    assert conflict_response.json()["detail"] == {"reason": "stale_revision"}
    assert conflict_response.json()["error"]["code"] == "state_conflict"
    assert conflict_response.json()["error"]["request_id"] == conflict_response.headers["X-Request-ID"]

    not_found_response = client.get("/_test/not-found")
    assert not_found_response.status_code == 404
    assert not_found_response.json()["detail"] == "Task not found"
    assert not_found_response.json()["error"]["code"] == "resource_not_found"


def test_http_exception_never_reflects_dynamic_exception_provider_or_policy_values():
    app = create_app()
    private_detail = "api_key=not-a-real-secret-must-not-be-returned"
    nested_sentinel = "provider body must not be echoed"

    def dynamic_string():
        raise HTTPException(status_code=503, detail=private_detail)

    def dynamic_object():
        raise HTTPException(
            status_code=409,
            detail={
                "code": "provider_error",
                "message": nested_sentinel,
                "request": {"authorization": "Bearer private"},
            },
        )

    app.add_api_route("/_test/dynamic-string", dynamic_string, methods=["GET"])
    app.add_api_route("/_test/dynamic-object", dynamic_object, methods=["GET"])
    client = TestClient(app)

    string_response = client.get("/_test/dynamic-string")
    assert string_response.status_code == 503
    assert string_response.json()["detail"] == "The service is temporarily unavailable."
    assert private_detail not in string_response.text

    object_response = client.get("/_test/dynamic-object")
    assert object_response.status_code == 409
    assert object_response.json()["detail"] == (
        "The requested operation conflicts with the current state."
    )
    assert nested_sentinel not in object_response.text
    assert "Bearer private" not in object_response.text
    assert object_response.json()["error"]["request_id"] == object_response.headers["X-Request-ID"]


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


def test_policy_decision_detail_preserves_only_reviewed_fields():
    app = create_app()
    private_reason = "Missing required permission grants: cloudflare.read"
    correlation_id = "6b4c2fa1-42c9-4ae1-bbdf-f3bf9f5d2b47"

    def denied():
        raise HTTPException(
            status_code=403,
            detail={
                "decision": "deny",
                "reason": private_reason,
                "correlation_id": correlation_id,
                "private": "must-not-be-reflected",
            },
        )

    def approval_required():
        raise HTTPException(
            status_code=409,
            detail={
                "decision": "require_approval",
                "reason": "owner approval for action payload",
                "correlation_id": "not-a-canonical-uuid",
            },
        )

    app.add_api_route("/_test/policy-denied", denied, methods=["GET"])
    app.add_api_route("/_test/policy-approval", approval_required, methods=["GET"])
    client = TestClient(app)

    denied_response = client.get("/_test/policy-denied")
    assert denied_response.status_code == 403
    assert denied_response.json()["detail"] == {
        "decision": "deny",
        "reason": "The requested action is not permitted.",
        "correlation_id": correlation_id,
    }
    assert private_reason not in denied_response.text
    assert "must-not-be-reflected" not in denied_response.text

    approval_response = client.get("/_test/policy-approval")
    assert approval_response.status_code == 409
    assert approval_response.json()["detail"] == {
        "decision": "require_approval",
        "reason": "Explicit owner approval is required.",
    }
    assert "owner approval for action payload" not in approval_response.text


def test_reviewed_structured_error_details_are_sanitized_without_losing_contract_fields():
    from mrhub.api.errors import _safe_http_detail

    assert _safe_http_detail(
        409,
        {
            "code": "renderer_timeline_not_saved",
            "message": "Prepare and save the renderer timeline in the Hub dashboard first",
            "private": "must-not-leak",
        },
    ) == {
        "code": "renderer_timeline_not_saved",
        "message": "A saved renderer timeline is required before submitting a render.",
    }

    assert _safe_http_detail(
        409,
        {
            "code": "generation_cancellation_conflict",
            "message": "provider internal state and request data",
        },
    ) == {
        "code": "generation_cancellation_conflict",
        "message": "Active or ambiguous provider work cannot be cancelled through this endpoint.",
    }

    assert _safe_http_detail(
        429,
        {
            "code": "kimi_rate_limited",
            "message": "caller-controlled message",
            "retry_after_seconds": 37,
            "api_key": "must-not-leak",
        },
    ) == {
        "code": "kimi_rate_limited",
        "message": "Kimi requests are temporarily rate limited.",
        "retry_after_seconds": 37,
    }

    assert _safe_http_detail(
        403, {"reason_code": "authorization_scope_denied", "asset": "private-asset"}
    ) == {"reason_code": "authorization_scope_denied"}

    sanitized_profile_error = _safe_http_detail(
        404,
        {
            "message": "Unknown model profile ID(s)",
            "profile_ids": ["unknown-profile", "ghp_secret-token-like-value"],
        },
    )
    assert sanitized_profile_error == {"message": "Unknown model profile ID(s)"}
    assert "unknown-profile" not in str(sanitized_profile_error)
    assert "ghp_secret-token-like-value" not in str(sanitized_profile_error)

    assert _safe_http_detail(
        409,
        {"code": "unrecognized_code", "message": "untrusted dynamic detail"},
    ) == "The requested operation conflicts with the current state."
