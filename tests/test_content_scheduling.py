from datetime import UTC, datetime, timedelta

from client_helpers import authenticated_client


def _create_draft(client, platform: str = "telegram") -> dict[str, object]:
    response = client.post(
        "/content/drafts",
        json={
            "platform": platform,
            "content_type": "post_text" if platform == "telegram" else "caption",
            "title": "Scheduled learning post",
            "body": "A short educational post about DNS records and troubleshooting.",
            "hashtags": ["#DNS"],
        },
    )
    assert response.status_code == 201
    return response.json()


def test_schedule_requires_approval_and_persists_owner_scoped_record() -> None:
    client = authenticated_client()
    draft = _create_draft(client)
    scheduled_at = (datetime.now(UTC) + timedelta(days=1)).isoformat()

    denied = client.post(
        f"/content/drafts/{draft['draft_id']}/schedule",
        json={"scheduled_at": scheduled_at},
    )
    assert denied.status_code == 409

    approved = client.post(f"/content/drafts/{draft['draft_id']}/approve")
    assert approved.status_code == 200
    created = client.post(
        f"/content/drafts/{draft['draft_id']}/schedule",
        json={"scheduled_at": scheduled_at},
    )
    assert created.status_code == 201
    schedule = created.json()
    assert schedule["status"] == "scheduled"
    assert schedule["platform"] == "telegram"
    assert schedule["draft_version"] == 1
    assert schedule["content_hash"] == draft["content_hash"]
    assert schedule["attempt_count"] == 0
    assert "body" not in schedule

    listing = client.get("/content/schedules")
    assert listing.status_code == 200
    assert listing.json()["count"] == 1
    assert listing.json()["schedules"][0]["schedule_id"] == schedule["schedule_id"]


def test_schedule_rejects_past_times_duplicate_active_schedule_and_generic_platform() -> None:
    client = authenticated_client()
    draft = _create_draft(client)
    client.post(f"/content/drafts/{draft['draft_id']}/approve")

    past = client.post(
        f"/content/drafts/{draft['draft_id']}/schedule",
        json={"scheduled_at": (datetime.now(UTC) - timedelta(minutes=1)).isoformat()},
    )
    assert past.status_code == 409

    future = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    first = client.post(
        f"/content/drafts/{draft['draft_id']}/schedule",
        json={"scheduled_at": future},
    )
    assert first.status_code == 201
    duplicate = client.post(
        f"/content/drafts/{draft['draft_id']}/schedule",
        json={"scheduled_at": future},
    )
    assert duplicate.status_code == 409

    generic = _create_draft(client, platform="generic")
    client.post(f"/content/drafts/{generic['draft_id']}/approve")
    unsupported = client.post(
        f"/content/drafts/{generic['draft_id']}/schedule",
        json={"scheduled_at": future},
    )
    assert unsupported.status_code == 409


def test_schedule_can_be_cancelled_only_while_pending() -> None:
    client = authenticated_client()
    draft = _create_draft(client)
    client.post(f"/content/drafts/{draft['draft_id']}/approve")
    created = client.post(
        f"/content/drafts/{draft['draft_id']}/schedule",
        json={"scheduled_at": (datetime.now(UTC) + timedelta(days=1)).isoformat()},
    )
    schedule_id = created.json()["schedule_id"]

    cancelled = client.post(f"/content/schedules/{schedule_id}/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"

    repeated = client.post(f"/content/schedules/{schedule_id}/cancel")
    assert repeated.status_code == 409


def test_schedule_api_requires_authentication() -> None:
    from fastapi.testclient import TestClient

    from mrhub.config import get_settings
    from mrhub.main import create_app

    get_settings.cache_clear()
    client = TestClient(create_app())
    assert client.get("/content/schedules").status_code in (401, 403)
    get_settings.cache_clear()
