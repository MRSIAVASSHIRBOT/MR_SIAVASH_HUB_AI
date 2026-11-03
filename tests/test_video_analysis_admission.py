import sqlite3

from client_helpers import authenticated_client, run_worker_once
from mrhub.config import get_settings


def _upload_video(client):
    response = client.post(
        "/content/assets",
        headers={
            "X-File-Name": "admission-test.mp4",
            "Content-Type": "video/mp4",
        },
        content=b"\x00\x00\x00\x18ftypisom0000",
    )
    assert response.status_code == 201
    return response.json()["asset_id"]


def _submit(client, asset_ids, key):
    return client.post(
        "/video-intelligence/analyses",
        headers={"Idempotency-Key": key},
        json={
            "mode": "faithful_style_reconstruction",
            "source_asset_ids": asset_ids,
            "duration_seconds": 20,
        },
    )


def _set_asset_status(asset_id, status):
    with sqlite3.connect(get_settings().database_path) as connection:
        connection.execute(
            "UPDATE content_assets SET processing_status = ? WHERE asset_id = ?",
            (status, asset_id),
        )


def test_analysis_api_rejects_assets_that_are_still_processing():
    client = authenticated_client()
    asset_id = _upload_video(client)
    _set_asset_status(asset_id, "processing")

    response = _submit(client, [asset_id], "asset-processing")

    assert response.status_code == 409
    assert response.json()["detail"] == "Source asset is not ready for analysis"


def test_analysis_worker_rechecks_source_readiness_after_admission():
    client = authenticated_client()
    asset_id = _upload_video(client)
    accepted = _submit(client, [asset_id], "worker-readiness")
    assert accepted.status_code == 202
    analysis_id = accepted.json()["analysis_id"]

    # Simulate another operation beginning a transcode after admission but
    # before a worker claims the analysis task.
    _set_asset_status(asset_id, "processing")
    completed = run_worker_once()

    assert completed is not None
    assert completed.status.value == "failed"
    analysis = client.get(f"/video-intelligence/analyses/{analysis_id}")
    assert analysis.status_code == 200
    assert analysis.json()["status"] == "failed"
    assert analysis.json()["error_code"] == "asset_not_ready"


def test_analysis_api_returns_idempotent_replay_before_capacity_check():
    client = authenticated_client()
    asset_id = _upload_video(client)

    first = _submit(client, [asset_id], "analysis-idempotent-replay")
    replay = _submit(client, [asset_id], "analysis-idempotent-replay")

    assert first.status_code == 202
    assert replay.status_code == 200
    assert replay.json()["analysis_id"] == first.json()["analysis_id"]
    assert replay.json()["created"] is False


def test_analysis_api_returns_429_when_owner_active_capacity_is_full(monkeypatch):
    from mrhub.video_intelligence import jobs as video_jobs

    monkeypatch.setattr(video_jobs, "MAX_ACTIVE_VIDEO_ANALYSES_PER_OWNER", 1)
    client = authenticated_client()
    asset_id = _upload_video(client)

    first = _submit(client, [asset_id], "owner-capacity-first")
    second = _submit(client, [asset_id], "owner-capacity-second")

    assert first.status_code == 202
    assert second.status_code == 429
    assert second.json()["detail"] == "Video analysis capacity is temporarily full"


def test_analysis_api_rejects_duplicate_source_asset_ids():
    client = authenticated_client()
    asset_id = _upload_video(client)

    response = _submit(
        client,
        [asset_id, asset_id],
        "duplicate-source-assets",
    )

    assert response.status_code == 422
