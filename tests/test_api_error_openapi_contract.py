import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from mrhub.main import create_app


def test_openapi_documents_common_error_contract_on_mounted_routes():
    client = TestClient(create_app())
    response = client.get("/openapi.json")

    assert response.status_code == 200
    schema = response.json()
    components = schema["components"]["schemas"]
    assert "APIErrorResponse" in components
    assert "APIErrorEnvelope" in components
    assert "APIErrorIssue" in components

    operation = schema["paths"]["/agent/workflows"]["post"]
    statuses = ("401", "403", "404", "409", "422", "429", "500", "503", "default")
    for status in statuses:
        error_schema = operation["responses"][status]["content"]["application/json"]["schema"]
        assert error_schema["$ref"] == "#/components/schemas/APIErrorResponse"


def test_error_response_models_preserve_legacy_detail_and_type_validation_issues():
    from mrhub.api.errors import APIErrorEnvelope, APIErrorIssue, APIErrorResponse

    response = APIErrorResponse(
        detail=[{"loc": ["body", "name"], "msg": "Invalid request value", "type": "missing"}],
        error=APIErrorEnvelope(
            code="request_validation_error",
            message="The request contains invalid fields.",
            request_id="12345678-1234-5678-1234-567812345678",
            issues=[
                APIErrorIssue(
                    location=["body", "name"],
                    code="missing",
                    message="Invalid request value",
                )
            ],
        ),
    )

    dumped = response.model_dump(mode="json", exclude_none=True)
    assert dumped["detail"][0]["loc"] == ["body", "name"]
    assert dumped["error"]["issues"][0] == {
        "location": ["body", "name"],
        "code": "missing",
        "message": "Invalid request value",
    }



def test_error_envelope_rejects_noncanonical_request_ids():
    from mrhub.api.errors import APIErrorEnvelope

    with pytest.raises(ValidationError):
        APIErrorEnvelope(
            code="internal_error",
            message="An internal error occurred.",
            request_id="not-a-canonical-uuid-value-000000",
        )
