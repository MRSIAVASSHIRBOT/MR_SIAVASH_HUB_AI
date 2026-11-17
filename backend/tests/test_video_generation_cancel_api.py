from uuid import uuid4

from client_helpers import authenticated_client
from mrhub.video_intelligence.generation_jobs import VideoGenerationJobRepository


def test_cancel_generation_route_cancels_owner_pending_job(monkeypatch):
    generation_id = uuid4()
    calls = []

    def request_cancellation(self, owner_user_id, requested_id):
        calls.append((owner_user_id, requested_id))
        return {
            "generation_id": str(requested_id),
            "status": "cancelled",
            "cancellation_requested": False,
        }

    monkeypatch.setattr(VideoGenerationJobRepository, "request_cancellation", request_cancellation)
    client = authenticated_client()
    try:
        response = client.delete(f"/video-intelligence/generations/{generation_id}")
    finally:
        client.close()

    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"
    assert calls == [("local-owner", generation_id)]


def test_cancel_generation_route_returns_not_found_for_foreign_or_missing_job(
    monkeypatch,
):
    monkeypatch.setattr(
        VideoGenerationJobRepository,
        "request_cancellation",
        lambda self, owner_user_id, generation_id: None,
    )
    client = authenticated_client()
    try:
        response = client.delete(f"/video-intelligence/generations/{uuid4()}")
    finally:
        client.close()

    assert response.status_code == 404


def test_cancel_generation_route_queues_provider_cancellation_for_active_job(monkeypatch):
    generation_id = uuid4()
    calls = []

    def request_cancellation(self, owner_user_id, requested_id):
        calls.append((owner_user_id, requested_id))
        return {
            "generation_id": str(requested_id),
            "status": "running",
            "cancellation_requested": True,
            "created": True,
            "execution": "provider_cancellation_queued",
        }

    monkeypatch.setattr(
        VideoGenerationJobRepository, "request_cancellation", request_cancellation
    )
    client = authenticated_client()
    try:
        response = client.delete(f"/video-intelligence/generations/{generation_id}")
    finally:
        client.close()

    assert response.status_code == 202
    assert response.json()["status"] == "running"
    assert response.json()["cancellation_requested"] is True
    assert response.json()["execution"] == "provider_cancellation_queued"
    assert calls == [("local-owner", generation_id)]



def test_generation_history_route_returns_bounded_owner_page(monkeypatch):
    from mrhub.video_intelligence.generation_jobs import VideoGenerationJobRepository

    calls = []
    rows = [
        {
            "generation_id": str(uuid4()),
            "source_analysis_id": str(uuid4()),
            "provider": "local",
            "model": "renderer-v1",
            "status": "queued",
            "progress_percent": None,
            "output_asset_id": None,
            "output_bytes": None,
            "output_duration_seconds": None,
            "output_width": None,
            "output_height": None,
            "error_code": None,
            "created_at": "2026-11-15T12:00:00+00:00",
            "updated_at": "2026-11-15T12:00:00+00:00",
        }
    ]

    def list_for_owner(
        self, owner_user_id, *, limit=20, before_created_at=None,
        before_generation_id=None
    ):
        calls.append(
            (owner_user_id, limit, before_created_at, before_generation_id)
        )
        return rows

    monkeypatch.setattr(
        VideoGenerationJobRepository, "list_for_owner", list_for_owner
    )
    client = authenticated_client()
    try:
        response = client.get("/video-intelligence/generations?limit=10")
    finally:
        client.close()

    assert response.status_code == 200
    expected_rows = [{**rows[0], "cancellation_requested": False}]
    assert response.json() == {"items": expected_rows, "next_cursor": None}
    assert calls == [("local-owner", 11, None, None)]


def test_generation_history_route_rejects_partial_or_timezone_naive_cursor():
    client = authenticated_client()
    try:
        partial = client.get(
            "/video-intelligence/generations",
            params={"before_created_at": "2026-11-15T12:00:00+00:00"},
        )
        naive = client.get(
            "/video-intelligence/generations",
            params={
                "before_created_at": "2026-11-15T12:00:00",
                "before_generation_id": str(uuid4()),
            },
        )
    finally:
        client.close()

    assert partial.status_code == 422
    assert naive.status_code == 422



def test_generation_history_route_emits_next_cursor_only_when_more_results_exist(
    monkeypatch,
):
    from mrhub.video_intelligence.generation_jobs import VideoGenerationJobRepository

    first_id, second_id = sorted((uuid4(), uuid4()), key=str, reverse=True)
    rows = [
        {
            "generation_id": str(first_id),
            "source_analysis_id": str(uuid4()),
            "provider": "local",
            "model": "renderer-v1",
            "status": "succeeded",
            "progress_percent": 100,
            "output_asset_id": str(uuid4()),
            "output_bytes": 4096,
            "output_duration_seconds": 5.0,
            "output_width": 1080,
            "output_height": 1920,
            "error_code": None,
            "created_at": "2026-11-15T12:00:00+00:00",
            "updated_at": "2026-11-15T12:01:00+00:00",
        },
        {
            "generation_id": str(second_id),
            "source_analysis_id": str(uuid4()),
            "provider": "local",
            "model": "renderer-v1",
            "status": "queued",
            "progress_percent": None,
            "output_asset_id": None,
            "output_bytes": None,
            "output_duration_seconds": None,
            "output_width": None,
            "output_height": None,
            "error_code": None,
            "created_at": "2026-11-15T12:00:00+00:00",
            "updated_at": "2026-11-15T12:00:00+00:00",
        },
    ]
    monkeypatch.setattr(
        VideoGenerationJobRepository,
        "list_for_owner",
        lambda self, owner_user_id, **kwargs: rows,
    )
    client = authenticated_client()
    try:
        response = client.get("/video-intelligence/generations?limit=1")
    finally:
        client.close()

    assert response.status_code == 200
    payload = response.json()
    assert payload["items"] == [{**rows[0], "cancellation_requested": False}]
    assert payload["next_cursor"] == {
        "before_created_at": rows[0]["created_at"],
        "before_generation_id": rows[0]["generation_id"],
    }
