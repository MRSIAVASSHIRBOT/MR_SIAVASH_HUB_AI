from client_helpers import authenticated_client, run_worker_once
from mrhub.video_intelligence import scenes, service
from mrhub.video_intelligence.scenes import SceneDetectionResult
from mrhub.video_intelligence.schemas import VideoTechnicalMetadata


def _upload_video(client):
    response = client.post(
        "/content/assets",
        headers={
            "X-File-Name": "scene-test.mp4",
            "Content-Type": "video/mp4",
        },
        content=b"\x00\x00\x00\x18ftypisom0000",
    )
    assert response.status_code == 201
    return response.json()["asset_id"]


def test_scene_job_api_queues_runs_and_returns_sanitized_result(monkeypatch):
    client = authenticated_client()
    asset_id = _upload_video(client)

    accepted = client.post(
        f"/video-intelligence/assets/{asset_id}/scene-jobs",
        json={"threshold": 0.35, "max_scene_changes": 10},
    )
    assert accepted.status_code == 202
    job_id = accepted.json()["job_id"]
    queued = client.get(f"/video-intelligence/scene-jobs/{job_id}")
    assert queued.status_code == 200
    assert queued.json()["status"] == "queued"
    assert queued.json()["result"] is None
    assert queued.json()["threshold"] == 0.35
    assert queued.json()["max_scene_changes"] == 10

    monkeypatch.setattr(
        service,
        "probe_video",
        lambda _path: VideoTechnicalMetadata(
            duration_seconds=5.0,
            width=1920,
            height=1080,
            frame_rate=30,
            codec="h264",
            has_audio=True,
            metadata_status="available",
        ),
    )
    monkeypatch.setattr(
        scenes,
        "detect_scene_boundaries",
        lambda *_args, **_kwargs: SceneDetectionResult(
            scene_start_times=(0.0, 2.25, 4.0),
            truncated=False,
        ),
    )

    completed = run_worker_once()
    assert completed is not None
    assert completed.status.value == "succeeded"

    result = client.get(f"/video-intelligence/scene-jobs/{job_id}")
    assert result.status_code == 200
    assert result.json()["status"] == "succeeded"
    assert result.json()["result"] == {
        "scene_start_times": [0.0, 2.25, 4.0],
        "scene_count": 3,
        "truncated": False,
    }
    assert "storage_key" not in result.json()
    assert "owner_user_id" not in result.json()
    assert "task_id" not in result.json()


def test_scene_job_api_validates_bounds_and_media_type():
    client = authenticated_client()
    asset_id = _upload_video(client)

    invalid_threshold = client.post(
        f"/video-intelligence/assets/{asset_id}/scene-jobs",
        json={"threshold": 1.2},
    )
    assert invalid_threshold.status_code == 422

    invalid_cap = client.post(
        f"/video-intelligence/assets/{asset_id}/scene-jobs",
        json={"max_scene_changes": 25},
    )
    assert invalid_cap.status_code == 422

    image = client.post(
        "/content/assets",
        headers={"X-File-Name": "poster.png", "Content-Type": "image/png"},
        content=b"\x89PNG\r\n\x1a\nimage",
    )
    assert image.status_code == 201
    rejected = client.post(
        f"/video-intelligence/assets/{image.json()['asset_id']}/scene-jobs",
        json={},
    )
    assert rejected.status_code == 415


def test_scene_job_api_enforces_owner_active_capacity():
    client = authenticated_client()
    asset_id = _upload_video(client)

    first = client.post(f"/video-intelligence/assets/{asset_id}/scene-jobs", json={})
    second = client.post(f"/video-intelligence/assets/{asset_id}/scene-jobs", json={})
    third = client.post(f"/video-intelligence/assets/{asset_id}/scene-jobs", json={})

    assert first.status_code == 202
    assert second.status_code == 202
    assert third.status_code == 429


def test_scene_job_api_cancels_only_existing_owner_job():
    client = authenticated_client()
    asset_id = _upload_video(client)
    accepted = client.post(
        f"/video-intelligence/assets/{asset_id}/scene-jobs",
        json={},
    )
    job_id = accepted.json()["job_id"]

    cancelled = client.post(f"/video-intelligence/scene-jobs/{job_id}/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"

    terminal = client.post(f"/video-intelligence/scene-jobs/{job_id}/cancel")
    assert terminal.status_code == 409

def test_scene_jobs_are_hidden_from_generic_task_and_job_endpoints():
    import sqlite3

    from mrhub.config import get_settings

    client = authenticated_client()
    asset_id = _upload_video(client)
    accepted = client.post(
        f"/video-intelligence/assets/{asset_id}/scene-jobs",
        json={},
    )
    assert accepted.status_code == 202
    job_id = accepted.json()["job_id"]

    with sqlite3.connect(get_settings().database_path) as connection:
        row = connection.execute(
            "SELECT task_id FROM video_scene_jobs WHERE job_id = ?",
            (job_id,),
        ).fetchone()
    assert row is not None
    task_id = row[0]

    assert client.get(f"/tasks/{task_id}").status_code == 404
    assert client.get(f"/tasks/{task_id}/result").status_code == 404
    assert client.post(f"/jobs/{task_id}/cancel").status_code == 404
    listed = client.get("/tasks").json()
    assert all(task["task_id"] != task_id for task in listed)
    owner_view = client.get(f"/video-intelligence/scene-jobs/{job_id}")
    assert owner_view.status_code == 200
    assert owner_view.json()["status"] == "queued"

