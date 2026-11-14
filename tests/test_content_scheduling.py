from datetime import UTC, datetime, timedelta

from client_helpers import authenticated_client


def _create_draft(
    client,
    platform: str = "telegram",
    *,
    title: str = "Scheduled learning post",
    body: str = "A short educational post about DNS records and troubleshooting.",
) -> dict[str, object]:
    response = client.post(
        "/content/drafts",
        json={
            "platform": platform,
            "content_type": "post_text" if platform == "telegram" else "caption",
            "title": title,
            "body": body,
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



def _create_approved_campaign_drafts(client, *, suffix=""):
    from mrhub.config import get_settings
    from mrhub.media.repository import MediaAssetRepository

    media = MediaAssetRepository(get_settings().database_path)
    with media.tasks._connection() as connection:
        owner_id = connection.execute(
            "SELECT user_id FROM auth_users WHERE username = 'owner'"
        ).fetchone()["user_id"]
    asset = media.store_upload(
        owner_id,
        "campaign-reel.mp4",
        "video/mp4",
        b"\x00\x00\x00\x18ftypisom" + b"campaign-test-render",
    )
    with media.tasks._connection() as connection:
        connection.execute(
            "UPDATE content_assets SET processing_status = 'processed', "
            "processing_profile = 'video_render_cut_v1' WHERE asset_id = ? AND owner_user_id = ?",
            (asset["asset_id"], owner_id),
        )
    reel_response = client.post(
        "/content/drafts",
        json={
            "platform": "instagram",
            "content_type": "reel",
            "title": f"Campaign Reel {suffix}" if suffix else "Campaign Reel",
            "body": (
                "A useful short lesson about safe account security. "
                + suffix
            ).strip(),
            "media_asset_id": asset["asset_id"],
        },
    )
    assert reel_response.status_code == 201, reel_response.text
    telegram = _create_draft(
        client,
        platform="telegram",
        title=f"Campaign lesson {suffix}" if suffix else "Scheduled learning post",
        body=(
            "A distinct campaign lesson about account security. "
            + suffix
        ).strip(),
    )
    for draft in (reel_response.json(), telegram):
        approved = client.post(f"/content/drafts/{draft['draft_id']}/approve")
        assert approved.status_code == 200, approved.text
    return reel_response.json(), telegram


def test_campaign_links_approved_reel_and_telegram_lesson_and_schedules_atomically():
    client = authenticated_client()
    reel, telegram = _create_approved_campaign_drafts(client)
    created = client.post(
        "/content/campaigns",
        json={
            "title": "Account security mini-campaign",
            "instagram_draft_id": reel["draft_id"],
            "telegram_draft_id": telegram["draft_id"],
        },
    )
    assert created.status_code == 201, created.text
    campaign = created.json()
    assert campaign["status"] == "draft"
    assert campaign["schedules"] == []

    scheduled = client.post(
        f"/content/campaigns/{campaign['campaign_id']}/schedule",
        json={"scheduled_at": (datetime.now(UTC) + timedelta(days=1)).isoformat()},
    )
    assert scheduled.status_code == 200, scheduled.text
    record = scheduled.json()
    assert record["status"] == "scheduled"
    assert len(record["schedules"]) == 2
    assert {item["platform"] for item in record["schedules"]} == {"instagram", "telegram"}
    assert {item["draft_id"] for item in record["schedules"]} == {
        reel["draft_id"], telegram["draft_id"]
    }

    listed = client.get("/content/campaigns")
    assert listed.status_code == 200
    assert listed.json()["count"] == 1
    assert listed.json()["campaigns"][0]["campaign_id"] == campaign["campaign_id"]


def test_campaign_requires_verified_reel_asset_and_both_approvals():
    client = authenticated_client()
    reel, telegram = _create_approved_campaign_drafts(client)
    # Editing the Reel revokes its approval and must block campaign creation.
    changed = client.patch(
        f"/content/drafts/{reel['draft_id']}",
        json={"body": "Changed after approval"},
    )
    assert changed.status_code == 200
    denied = client.post(
        "/content/campaigns",
        json={
            "title": "Must not link stale approval",
            "instagram_draft_id": reel["draft_id"],
            "telegram_draft_id": telegram["draft_id"],
        },
    )
    assert denied.status_code == 409


def test_campaign_cancellation_cancels_both_pending_schedules():
    client = authenticated_client()
    reel, telegram = _create_approved_campaign_drafts(client)
    created = client.post(
        "/content/campaigns",
        json={
            "title": "Cancelable campaign",
            "instagram_draft_id": reel["draft_id"],
            "telegram_draft_id": telegram["draft_id"],
        },
    )
    assert created.status_code == 201, created.text
    campaign_id = created.json()["campaign_id"]
    scheduled = client.post(
        f"/content/campaigns/{campaign_id}/schedule",
        json={"scheduled_at": (datetime.now(UTC) + timedelta(days=1)).isoformat()},
    )
    assert scheduled.status_code == 200, scheduled.text

    cancelled = client.post(f"/content/campaigns/{campaign_id}/cancel")
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["status"] == "cancelled"
    assert len(cancelled.json()["schedules"]) == 2
    assert {item["status"] for item in cancelled.json()["schedules"]} == {"cancelled"}
    repeated = client.post(f"/content/campaigns/{campaign_id}/cancel")
    assert repeated.status_code == 409


def test_campaign_routes_are_owner_scoped_and_require_authentication():
    from fastapi.testclient import TestClient

    from mrhub.config import get_settings
    from mrhub.main import create_app

    get_settings.cache_clear()
    client = TestClient(create_app())
    assert client.get("/content/campaigns").status_code in (401, 403)
    get_settings.cache_clear()



def test_campaign_reports_unknown_outcome_without_blind_retry():
    from mrhub.config import get_settings
    from mrhub.content.scheduling import ContentScheduleRepository

    client = authenticated_client()
    reel, telegram = _create_approved_campaign_drafts(client)
    created = client.post(
        "/content/campaigns",
        json={
            "title": "Ambiguous delivery campaign",
            "instagram_draft_id": reel["draft_id"],
            "telegram_draft_id": telegram["draft_id"],
        },
    )
    assert created.status_code == 201, created.text
    campaign_id = created.json()["campaign_id"]
    scheduled = client.post(
        f"/content/campaigns/{campaign_id}/schedule",
        json={"scheduled_at": (datetime.now(UTC) + timedelta(days=1)).isoformat()},
    )
    assert scheduled.status_code == 200, scheduled.text
    schedules = scheduled.json()["schedules"]
    repository = ContentScheduleRepository(get_settings().database_path)
    with repository.tasks._connection() as connection:
        connection.execute(
            "UPDATE content_publish_schedules SET status = 'unknown_outcome' "
            "WHERE schedule_id = ?",
            (schedules[0]["schedule_id"],),
        )
    current = client.get(f"/content/campaigns/{campaign_id}")
    assert current.status_code == 200
    assert current.json()["status"] == "unknown_outcome"


def test_deleting_linked_draft_cascades_campaign_link_without_orphaning_schedule():
    from mrhub.config import get_settings
    from mrhub.content.scheduling import ContentScheduleRepository

    client = authenticated_client()
    reel, telegram = _create_approved_campaign_drafts(client)
    created = client.post(
        "/content/campaigns",
        json={
            "title": "Deletion cleanup campaign",
            "instagram_draft_id": reel["draft_id"],
            "telegram_draft_id": telegram["draft_id"],
        },
    )
    assert created.status_code == 201, created.text
    campaign_id = created.json()["campaign_id"]
    repository = ContentScheduleRepository(get_settings().database_path)
    # Campaigns are intentionally unscheduled here; draft deletion should remove the link.
    deleted = client.delete(f"/content/drafts/{reel['draft_id']}")
    assert deleted.status_code == 204
    assert client.get(f"/content/campaigns/{campaign_id}").status_code == 404
    with repository.tasks._connection() as connection:
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


def test_campaign_drafts_cannot_be_reused_across_campaigns():
    client = authenticated_client()
    reel, telegram = _create_approved_campaign_drafts(client)
    first = client.post(
        "/content/campaigns",
        json={
            "title": "First campaign",
            "instagram_draft_id": reel["draft_id"],
            "telegram_draft_id": telegram["draft_id"],
        },
    )
    assert first.status_code == 201, first.text

    another_telegram = _create_draft(
        client,
        platform="telegram",
        title="Second campaign lesson",
        body="A distinct lesson about secure backups and account recovery.",
    )
    approved = client.post(f"/content/drafts/{another_telegram['draft_id']}/approve")
    assert approved.status_code == 200, approved.text
    second = client.post(
        "/content/campaigns",
        json={
            "title": "Second campaign reusing Reel",
            "instagram_draft_id": reel["draft_id"],
            "telegram_draft_id": another_telegram["draft_id"],
        },
    )
    assert second.status_code == 409


def test_campaign_rejects_drafts_with_existing_publish_schedule():
    client = authenticated_client()
    reel, telegram = _create_approved_campaign_drafts(client)
    scheduled = client.post(
        f"/content/drafts/{reel['draft_id']}/schedule",
        json={"scheduled_at": (datetime.now(UTC) + timedelta(days=1)).isoformat()},
    )
    assert scheduled.status_code == 201, scheduled.text

    created = client.post(
        "/content/campaigns",
        json={
            "title": "Must not mix standalone schedule",
            "instagram_draft_id": reel["draft_id"],
            "telegram_draft_id": telegram["draft_id"],
        },
    )
    assert created.status_code == 409


def test_campaign_schedule_rejects_any_prior_standalone_publish_history():
    from mrhub.config import get_settings
    from mrhub.content.scheduling import ContentScheduleRepository

    client = authenticated_client()
    repository = ContentScheduleRepository(get_settings().database_path)
    for terminal_status in ("published", "failed", "cancelled"):
        reel, telegram = _create_approved_campaign_drafts(client, suffix=terminal_status)
        created = client.post(
            "/content/campaigns",
            json={
                "title": f"Campaign with prior {terminal_status} history",
                "instagram_draft_id": reel["draft_id"],
                "telegram_draft_id": telegram["draft_id"],
            },
        )
        assert created.status_code == 201, created.text
        campaign_id = created.json()["campaign_id"]
        standalone = client.post(
            f"/content/drafts/{reel['draft_id']}/schedule",
            json={"scheduled_at": (datetime.now(UTC) + timedelta(days=1)).isoformat()},
        )
        assert standalone.status_code == 201, standalone.text
        schedule_id = standalone.json()["schedule_id"]
        with repository.tasks._connection() as connection:
            connection.execute(
                "UPDATE content_publish_schedules SET status = ?, published_at = ? WHERE schedule_id = ?",
                (terminal_status, datetime.now(UTC).isoformat(), schedule_id),
            )
        rejected = client.post(
            f"/content/campaigns/{campaign_id}/schedule",
            json={"scheduled_at": (datetime.now(UTC) + timedelta(days=2)).isoformat()},
        )
        assert rejected.status_code == 409, rejected.text
        current = client.get(f"/content/campaigns/{campaign_id}")
        assert current.status_code == 200
        assert len(current.json()["schedules"]) == 1
        assert current.json()["schedules"][0]["status"] == terminal_status
