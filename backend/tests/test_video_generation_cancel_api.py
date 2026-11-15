from uuid import uuid4

import pytest

from client_helpers import authenticated_client
from mrhub.video_intelligence.generation_jobs import (
    VideoGenerationCancellationConflict,
    VideoGenerationJobRepository,
)


def test_cancel_generation_route_cancels_owner_pending_job(monkeypatch):
    generation_id = uuid4()
    calls = []

    def cancel_pending(self, owner_user_id, requested_id):
        calls.append((owner_user_id, requested_id))
        return {
            "generation_id": str(requested_id),
            "status": "cancelled",
            "cancellation_requested": False,
        }

    monkeypatch.setattr(VideoGenerationJobRepository, "cancel_pending", cancel_pending)
    client = authenticated_client()
    try:
        response = client.delete(f"/video-intelligence/generations/{generation_id}")
    finally:
        client.close()

    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"
    assert calls == [("owner-1", generation_id)]


def test_cancel_generation_route_returns_not_found_for_foreign_or_missing_job(
    monkeypatch,
):
    monkeypatch.setattr(
        VideoGenerationJobRepository,
        "cancel_pending",
        lambda self, owner_user_id, generation_id: None,
    )
    client = authenticated_client()
    try:
        response = client.delete(f"/video-intelligence/generations/{uuid4()}")
    finally:
        client.close()

    assert response.status_code == 404


def test_cancel_generation_route_rejects_active_provider_job(monkeypatch):
    def conflict(self, owner_user_id, generation_id):
        raise VideoGenerationCancellationConflict(
            "Active provider cancellation requires a provider-side cancellation workflow"
        )

    monkeypatch.setattr(VideoGenerationJobRepository, "cancel_pending", conflict)
    client = authenticated_client()
    try:
        response = client.delete(f"/video-intelligence/generations/{uuid4()}")
    finally:
        client.close()

    assert response.status_code == 409
    assert "provider-side cancellation workflow" in response.text
