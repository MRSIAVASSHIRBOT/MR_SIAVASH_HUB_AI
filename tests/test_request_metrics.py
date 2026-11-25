import json

from fastapi.testclient import TestClient

from client_helpers import authenticated_client
from mrhub.infrastructure.request_metrics import BUCKETS_MS, RequestMetrics
from mrhub.main import create_app


def test_request_metrics_count_requests_and_keep_fixed_latency_buckets():
    metrics = RequestMetrics()
    metrics.record("GET", "/health", 200, 2.5)
    metrics.record("POST", "/jobs/{task_id}/cancel", 409, 18.0)

    snapshot = metrics.snapshot()
    assert snapshot["scope"] == "single_process"
    assert snapshot["temporality"] == "cumulative_since_process_start"
    assert snapshot["bucket_upper_bounds_ms"] == list(BUCKETS_MS)
    by_route = {item["route_template"]: item for item in snapshot["series"]}

    assert by_route["/health"]["count"] == 1
    assert by_route["/health"]["duration_sum_ms"] == 2.5
    assert by_route["/health"]["bucket_counts"] == [1] * len(BUCKETS_MS)
    assert by_route["/jobs/{task_id}/cancel"]["count"] == 1
    assert by_route["/jobs/{task_id}/cancel"]["duration_sum_ms"] == 18.0
    assert by_route["/jobs/{task_id}/cancel"]["bucket_counts"][0:3] == [0, 0, 1]


def test_request_metrics_normalize_unknown_dimensions_and_drop_raw_paths():
    metrics = RequestMetrics()
    metrics.record("TRACE-UNBOUNDED-METHOD", "/private/user/123?token=secret", 503, 9.0)

    snapshot = metrics.snapshot()
    assert len(snapshot["series"]) == 1
    sample = snapshot["series"][0]
    assert sample["method"] == "OTHER"
    assert sample["route_template"] == "unmatched"
    assert sample["status_class"] == "5xx"
    assert "secret" not in json.dumps(snapshot)
    assert "/private/user/123" not in json.dumps(snapshot)


def test_request_metrics_enforce_series_limit_with_one_overflow_bucket():
    metrics = RequestMetrics(max_series=2)
    metrics.record("GET", "/health", 200, 2.0)
    metrics.record("POST", "/tasks", 201, 3.0)
    metrics.record("DELETE", "/memory", 204, 4.0)

    snapshot = metrics.snapshot()
    assert len(snapshot["series"]) == 2
    overflow = next(item for item in snapshot["series"] if item["route_template"] == "other")
    assert overflow["count"] == 2


def test_request_metrics_reject_invalid_series_limits():
    import pytest

    for invalid in (True, 0, -1, 1.5):
        with pytest.raises(ValueError):
            RequestMetrics(max_series=invalid)


def test_jobs_metrics_endpoint_requires_authentication():
    client = TestClient(create_app())

    response = client.get("/jobs/metrics")

    assert response.status_code in (401, 403)


def test_authenticated_metrics_api_uses_route_templates_not_query_or_path_values():
    client = authenticated_client()
    assert client.get("/health?email=private@example.invalid").status_code == 200
    assert client.post(
        "/jobs/not-a-uuid/cancel?token=do-not-record"
    ).status_code == 422

    response = client.get("/jobs/metrics")

    assert response.status_code == 200
    payload = response.json()
    assert payload["scope"] == "single_process"
    assert payload["temporality"] == "cumulative_since_process_start"
    serialized = json.dumps(payload)
    assert "/health" in serialized
    assert "/jobs/{task_id}/cancel" in serialized
    assert "private@example.invalid" not in serialized
    assert "do-not-record" not in serialized
    assert "not-a-uuid" not in serialized
