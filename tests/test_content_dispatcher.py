from datetime import UTC, datetime, timedelta

from client_helpers import authenticated_client
from mrhub.config import get_settings
from mrhub.content.dispatcher import (
    ContentScheduleDispatcher,
    PublishReceipt,
    UnknownPublishOutcome,
)


class ConfirmingAdapter:
    def publish(self, draft: dict[str, object], *, idempotency_key: str) -> PublishReceipt:
        assert draft["body"]
        assert idempotency_key
        return PublishReceipt(provider_post_id="provider-post-123")


class AmbiguousAdapter:
    def publish(self, draft: dict[str, object], *, idempotency_key: str) -> PublishReceipt:
        raise UnknownPublishOutcome("network response lost")


def _scheduled_due_post(client) -> dict[str, object]:
    draft_response = client.post(
        "/content/drafts",
        json={
            "platform": "telegram",
            "content_type": "post_text",
            "title": "Dispatcher test",
            "body": "A test post about safe publishing.",
            "hashtags": ["#Testing"],
        },
    )
    assert draft_response.status_code == 201
    draft = draft_response.json()
    approved = client.post(f"/content/drafts/{draft['draft_id']}/approve")
    assert approved.status_code == 200
    scheduled = client.post(
        f"/content/drafts/{draft['draft_id']}/schedule",
        json={"scheduled_at": (datetime.now(UTC) + timedelta(days=1)).isoformat()},
    )
    assert scheduled.status_code == 201
    record = scheduled.json()

    # Make it due using the isolated test database; production API rejects past timestamps.
    from mrhub.infrastructure.database import TaskRepository

    repository = TaskRepository(get_settings().database_path)
    with repository._connection() as connection:
        connection.execute(
            "UPDATE content_publish_schedules SET scheduled_at = ? WHERE schedule_id = ?",
            ((datetime.now(UTC) - timedelta(seconds=1)).isoformat(), record["schedule_id"]),
        )
    return record


def test_dispatcher_publishes_only_after_rechecking_approval_and_records_receipt() -> None:
    client = authenticated_client()
    schedule = _scheduled_due_post(client)
    dispatcher = ContentScheduleDispatcher(
        get_settings().database_path, adapters={"telegram": ConfirmingAdapter()}
    )

    result = dispatcher.run_once()

    assert result == {"schedule_id": schedule["schedule_id"], "status": "published"}
    listed = client.get("/content/schedules?status=published")
    assert listed.status_code == 200
    record = listed.json()["schedules"][0]
    assert record["provider_post_id"] == "provider-post-123"
    assert record["attempt_count"] == 1
    assert record["published_at"] is not None


def test_dispatcher_does_not_retry_ambiguous_provider_outcomes() -> None:
    client = authenticated_client()
    schedule = _scheduled_due_post(client)
    dispatcher = ContentScheduleDispatcher(
        get_settings().database_path, adapters={"telegram": AmbiguousAdapter()}
    )

    result = dispatcher.run_once()

    assert result == {
        "schedule_id": schedule["schedule_id"],
        "status": "unknown_outcome",
        "reason_code": "provider_outcome_unknown",
    }
    assert dispatcher.run_once() is None
    listed = client.get("/content/schedules?status=unknown_outcome")
    assert listed.json()["count"] == 1
    assert listed.json()["schedules"][0]["attempt_count"] == 1


def test_dispatcher_fails_closed_without_provider_adapter() -> None:
    client = authenticated_client()
    schedule = _scheduled_due_post(client)
    dispatcher = ContentScheduleDispatcher(get_settings().database_path)

    result = dispatcher.run_once()

    assert result == {
        "schedule_id": schedule["schedule_id"],
        "status": "failed",
        "reason_code": "provider_not_configured",
    }


def test_dispatcher_rejects_stale_draft_approval() -> None:
    client = authenticated_client()
    schedule = _scheduled_due_post(client)
    changed = client.patch(
        f"/content/drafts/{schedule['draft_id']}",
        json={"body": "Updated after approval; must not be published."},
    )
    assert changed.status_code == 200
    dispatcher = ContentScheduleDispatcher(
        get_settings().database_path, adapters={"telegram": ConfirmingAdapter()}
    )

    result = dispatcher.run_once()

    assert result == {
        "schedule_id": schedule["schedule_id"],
        "status": "failed",
        "reason_code": "draft_approval_stale",
    }
