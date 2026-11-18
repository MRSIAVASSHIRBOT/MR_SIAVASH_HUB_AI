import sqlite3
from uuid import UUID

import pytest
from fastapi import HTTPException

from client_helpers import authenticated_client, run_worker_once
from mrhub.api.routes.video_intelligence import cancel_video_scene_job, get_video_scene_job
from mrhub.config import get_settings
from mrhub.security.auth import AuthenticatedUser
from mrhub.video_intelligence import scene_worker
from mrhub.video_intelligence.scenes import SceneDetectionResult
from mrhub.video_intelligence.schemas import VideoTechnicalMetadata


def _upload_video(client):
    response = client.post(
        "/content/assets",
        headers={"X-File-Name": "scene-test.mp4", "Content-Type": "video/mp4"},
        content=b"\x00\x00\x00\x18ftypisom0000",
    )
    assert response.status_code == 201
    return response.json()["asset_id"]


def _submit(client, asset_id, key="scene-api-request"):
    return client.post(
        f"/video-intelligence/assets/{asset_id}/scene-jobs",
        headers={"Idempotency-Key": key},
        json={"threshold": 0.35, "max_scene_changes": 10},
    )


def test_scene_job_api_queues_runs_and_returns_owner_safe_result(monkeypatch):
    client = authenticated_client()
    asset_id = _upload_video(client)
    accepted = _submit(client, asset_id)
    assert accepted.status_code == 202
    job_id = accepted.json()["job_id"]
    assert "task_id" not in accepted.json()

    replay = _submit(client, asset_id)
    assert replay.status_code == 200
    assert replay.json()["job_id"] == job_id

    def fake_probe(_path):
        return VideoTechnicalMetadata(
            duration_seconds=5.0, width=1920, height=1080,
            frame_rate=30, codec="h264", has_audio=True,
            metadata_status="available",
        )

    monkeypatch.setattr(scene_worker, "probe_video", fake_probe)
    monkeypatch.setattr(
        scene_worker, "detect_scene_boundaries",
        lambda *_args, **_kwargs: SceneDetectionResult((0.0, 2.25, 4.0), truncated=False),
    )
    completed = run_worker_once()
    assert completed is not None and completed.status.value == "succeeded"

    result = client.get(f"/video-intelligence/scene-jobs/{job_id}")
    assert result.status_code == 200
    body = result.json()
    assert body["status"] == "succeeded"
    assert body["result"] == {
        "scene_start_times": [0.0, 2.25, 4.0],
        "scene_count": 3,
        "truncated": False,
    }
    assert "task_id" not in body
    assert "owner_user_id" not in body
    assert "source_asset_id" not in body
    assert "storage_key" not in body


def test_scene_job_api_validates_input_media_and_idempotency():
    client = authenticated_client()
    asset_id = _upload_video(client)
    missing_key = client.post(
        f"/video-intelligence/assets/{asset_id}/scene-jobs", json={}
    )
    assert missing_key.status_code == 422

    invalid_threshold = client.post(
        f"/video-intelligence/assets/{asset_id}/scene-jobs",
        headers={"Idempotency-Key": "bad-threshold"},
        json={"threshold": 1.2},
    )
    assert invalid_threshold.status_code == 422

    image = client.post(
        "/content/assets",
        headers={"X-File-Name": "poster.png", "Content-Type": "image/png"},
        content=b"\x89PNG\r\n\x1a\nimage",
    )
    assert image.status_code == 201
    rejected = _submit(client, image.json()["asset_id"], "image-source")
    assert rejected.status_code == 415


def test_scene_job_api_enforces_capacity_and_owner_isolation():
    client = authenticated_client()
    asset_id = _upload_video(client)
    first = _submit(client, asset_id, "capacity-one")
    second = _submit(client, asset_id, "capacity-two")
    third = _submit(client, asset_id, "capacity-three")
    assert first.status_code == 202
    assert second.status_code == 202
    assert third.status_code == 429

    job_id = UUID(first.json()["job_id"])
    other_user = AuthenticatedUser(user_id="different-owner", username="other")
    with pytest.raises(HTTPException) as read_error:
        get_video_scene_job(job_id, other_user)
    assert read_error.value.status_code == 404
    with pytest.raises(HTTPException) as cancel_error:
        cancel_video_scene_job(job_id, other_user)
    assert cancel_error.value.status_code == 404


def test_scene_job_api_cancels_only_owned_queued_job():
    client = authenticated_client()
    asset_id = _upload_video(client)
    accepted = _submit(client, asset_id, "cancel-one")
    assert accepted.status_code == 202
    cancelled = client.post(
        f"/video-intelligence/scene-jobs/{accepted.json()['job_id']}/cancel"
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    assert "task_id" not in cancelled.json()
    repeated = client.post(
        f"/video-intelligence/scene-jobs/{accepted.json()['job_id']}/cancel"
    )
    assert repeated.status_code == 409


def test_generic_task_routes_cannot_submit_or_discover_scene_jobs():
    client = authenticated_client()
    asset_id = _upload_video(client)
    accepted = _submit(client, asset_id, "generic-hide")
    assert accepted.status_code == 202
    with sqlite3.connect(get_settings().database_path) as connection:
        row = connection.execute(
            "SELECT task_id FROM video_scene_jobs WHERE job_id = ?",
            (accepted.json()["job_id"],),
        ).fetchone()
    assert row is not None
    task_id = row[0]

    forbidden = client.post("/tasks", json={
        "task_type": "video.scene_detection",
        "description": "must use the dedicated endpoint",
    })
    assert forbidden.status_code == 403
    assert client.get(f"/tasks/{task_id}").status_code == 404
    assert client.get(f"/tasks/{task_id}/result").status_code == 404
    assert client.post(f"/jobs/{task_id}/cancel").status_code == 404
    assert all(item["task_id"] != task_id for item in client.get("/tasks").json())
