from client_helpers import authenticated_client
from mrhub.config import get_settings


def test_high_risk_task_waits_for_approval(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("MRH_DATABASE_PATH", str(tmp_path / "approval.sqlite3"))
    get_settings.cache_clear()
    client = authenticated_client()
    response = client.post(
        "/tasks",
        json={"task_type": "content.publish"},
    )
    assert response.status_code == 201
    assert response.json()["status"] == "waiting_approval"
    get_settings.cache_clear()


def test_unknown_task_type_requires_approval(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("MRH_DATABASE_PATH", str(tmp_path / "unknown.sqlite3"))
    get_settings.cache_clear()
    client = authenticated_client()
    response = client.post(
        "/tasks",
        json={"task_type": "unregistered.action", "risk_class": "low"},
    )
    assert response.status_code == 201
    assert response.json()["status"] == "waiting_approval"
    assert response.json()["risk_class"] == "high"
    get_settings.cache_clear()


def test_job_cancel_endpoint(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("MRH_DATABASE_PATH", str(tmp_path / "cancel.sqlite3"))
    get_settings.cache_clear()
    client = authenticated_client()
    created = client.post("/tasks", json={"task_type": "demo.echo"})
    task_id = created.json()["task_id"]
    cancelled = client.post(f"/jobs/{task_id}/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    get_settings.cache_clear()


def test_policy_api_ignores_client_claimed_approval() -> None:
    client = authenticated_client()
    response = client.post(
        "/policy/evaluate",
        json={
            "action": "social.publish",
            "risk_class": "high",
            "external_side_effect": True,
            "user_approved": True,
        },
    )
    assert response.status_code == 200
    assert response.json()["decision"] == "require_approval"

def test_video_scene_task_type_is_reserved_for_owner_scoped_endpoint() -> None:
    client = authenticated_client()
    response = client.post(
        "/tasks",
        json={"task_type": "video.scene_detection"},
    )
    assert response.status_code == 403

