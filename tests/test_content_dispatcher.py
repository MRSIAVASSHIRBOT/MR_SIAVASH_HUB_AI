from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlsplit
from uuid import UUID

from client_helpers import authenticated_client
from mrhub.api.routes import public_media
from mrhub.config import get_settings
from mrhub.content.dispatcher import (
    ContentScheduleDispatcher,
    PublishReceipt,
    UnknownPublishOutcome,
)
from mrhub.domain.tasks import TaskRecord, TaskStatus
from mrhub.infrastructure.database import TaskRepository
from mrhub.jobs.worker import WorkerEngine
from mrhub.media.repository import MediaAssetRepository


class ConfirmingAdapter:
    def publish(self, draft: dict[str, object], *, idempotency_key: str) -> PublishReceipt:
        assert draft["body"]
        assert idempotency_key
        return PublishReceipt(provider_post_id="provider-post-123")


class AmbiguousAdapter:
    def publish(self, draft: dict[str, object], *, idempotency_key: str) -> PublishReceipt:
        raise UnknownPublishOutcome("network response lost")


def _scheduled_due_post(
    client,
    *,
    platform: str = "telegram",
    media_asset_id: str | None = None,
    body: str = "A test post about safe publishing.",
) -> dict[str, object]:
    draft_response = client.post(
        "/content/drafts",
        json={
            "platform": platform,
            "content_type": "caption" if platform == "instagram" else "post_text",
            "title": "Dispatcher test",
            "body": body,
            "hashtags": ["#Testing"],
            "media_asset_id": media_asset_id,
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



class InspectingInstagramAdapter:
    def __init__(self):
        self.draft = None

    def publish(self, draft: dict[str, object], *, idempotency_key: str) -> PublishReceipt:
        self.draft = draft
        assert idempotency_key
        return PublishReceipt(provider_post_id="instagram-post-456")


def test_instagram_dispatcher_passes_short_lived_signed_media_url(monkeypatch):
    monkeypatch.setenv("MRH_PUBLIC_MEDIA_BASE_URL", "https://media.example.com")
    monkeypatch.setenv("MRH_PUBLIC_MEDIA_SIGNING_KEY", "test-only-signing-key-0123456789abcdef")
    client = authenticated_client()
    uploaded = client.post(
        "/content/assets",
        content=b"\x89PNG\r\n\x1a\n" + b"test-image-data",
        headers={"Content-Type": "image/png", "X-File-Name": "approved.png"},
    )
    assert uploaded.status_code == 201
    asset_id = uploaded.json()["asset_id"]
    owner_id = uploaded.json()["owner_user_id"]
    media_repository = MediaAssetRepository(get_settings().database_path)
    stored_asset = media_repository.get(owner_id, UUID(asset_id))
    assert stored_asset is not None
    media_path = media_repository.file_path(str(stored_asset["storage_key"]))
    assert media_path.is_file()
    assert media_path.stat().st_size == stored_asset["file_size"]
    signed_url = public_media.sign_asset_url(asset_id)
    assert signed_url.startswith("https://media.example.com/public/media/")
    schedule = _scheduled_due_post(client, platform="instagram", media_asset_id=asset_id)
    adapter = InspectingInstagramAdapter()
    dispatcher = ContentScheduleDispatcher(
        get_settings().database_path, adapters={"instagram": adapter}
    )

    result = dispatcher.run_once()

    assert result == {"schedule_id": schedule["schedule_id"], "status": "published"}
    assert adapter.draft is not None
    media_url = adapter.draft["media_url"]
    assert isinstance(media_url, str)
    parsed = urlsplit(media_url)
    assert parsed.scheme == "https"
    assert parsed.netloc == "media.example.com"
    query = parse_qs(parsed.query)
    assert int(query["expires"][0]) > int(datetime.now(UTC).timestamp())
    assert len(query["signature"][0]) == 64
    assert "media_asset" not in adapter.draft

    # Exercise the actual public route through ASGI, not just its helper function.
    response = client.get(f"{parsed.path}?{parsed.query}")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["cache-control"] == "private, no-store"
    assert response.content.startswith(bytes([137, 80, 78, 71, 13, 10, 26, 10]))



def test_signed_media_rejects_tampered_signature_before_asset_lookup(monkeypatch):
    import time
    from uuid import uuid4

    monkeypatch.setenv("MRH_PUBLIC_MEDIA_SIGNING_KEY", "test-only-signing-key-0123456789abcdef")
    client = authenticated_client()
    asset_id = str(uuid4())
    expires = int(time.time()) + 120
    response = client.get(
        f"/public/media/{asset_id}?expires={expires}&signature={'0' * 64}"
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "invalid_media_signature"


def test_signed_media_rejects_expired_and_overlong_expiry_before_asset_lookup(monkeypatch):
    import time
    from uuid import uuid4

    monkeypatch.setenv("MRH_PUBLIC_MEDIA_SIGNING_KEY", "test-only-signing-key-0123456789abcdef")
    client = authenticated_client()
    asset_id = str(uuid4())
    signature = "0" * 64
    now = int(time.time())

    expired = client.get(
        f"/public/media/{asset_id}?expires={now}&signature={signature}"
    )
    too_far = client.get(
        f"/public/media/{asset_id}?expires={now + 905}&signature={signature}"
    )
    assert expired.status_code == 403
    assert expired.json()["detail"] == "media_url_expired"
    assert too_far.status_code == 403
    assert too_far.json()["detail"] == "media_url_expired"


def test_dispatcher_rechecks_emergency_stop_before_provider_side_effect(monkeypatch):
    client = authenticated_client()
    schedule = _scheduled_due_post(client)
    class CountingAdapter:
        def __init__(self):
            self.calls = 0

        def publish(self, draft: dict[str, object], *, idempotency_key: str) -> PublishReceipt:
            self.calls += 1
            return PublishReceipt(provider_post_id="should-not-be-created")

    adapter = CountingAdapter()
    dispatcher = ContentScheduleDispatcher(
        get_settings().database_path, adapters={"telegram": adapter}
    )
    checks = 0

    def stop_on_final_gate(connection=None):
        nonlocal checks
        checks += 1
        # First check is before claiming; second is inside the claim transaction.
        # The third is the last gate immediately before calling the provider.
        return checks >= 3

    monkeypatch.setattr(dispatcher._control, "is_stopped", stop_on_final_gate)
    result = dispatcher.run_once()

    assert result == {
        "schedule_id": schedule["schedule_id"],
        "status": "scheduled",
        "reason_code": "emergency_stop",
    }
    assert checks == 3
    assert adapter.calls == 0
    listed = client.get("/content/schedules?status=scheduled")
    assert listed.status_code == 200
    assert listed.json()["count"] == 1
    assert listed.json()["schedules"][0]["attempt_count"] == 1


def test_worker_processes_at_most_one_due_content_schedule_per_cycle():
    client = authenticated_client()
    first = _scheduled_due_post(client, body="First bounded worker-cycle test post.")
    second = _scheduled_due_post(client, body="Second bounded worker-cycle test post.")
    repository = TaskRepository(get_settings().database_path)
    queued_task = TaskRecord(task_type="demo.echo", description="worker cycle integration")
    repository.create(queued_task)

    class CountingAdapter:
        def __init__(self):
            self.calls = []

        def publish(self, draft: dict[str, object], *, idempotency_key: str) -> PublishReceipt:
            self.calls.append((draft["draft_id"], idempotency_key))
            return PublishReceipt(provider_post_id=f"provider-{len(self.calls)}")

    adapter = CountingAdapter()
    dispatcher = ContentScheduleDispatcher(
        get_settings().database_path, adapters={"telegram": adapter}
    )
    worker = WorkerEngine(repository, content_schedule_dispatcher=dispatcher)

    # One worker cycle may execute one task and at most one due content schedule.
    completed = worker.run_once()
    assert completed is not None
    assert completed.task_id == queued_task.task_id
    assert completed.status is TaskStatus.SUCCEEDED
    assert len(adapter.calls) == 1

    # The next cycle drains only the next due schedule; no hidden batch dispatch occurs.
    assert worker.run_once() is None
    assert len(adapter.calls) == 2
    assert worker.run_once() is None
    assert len(adapter.calls) == 2

    published = client.get("/content/schedules?status=published")
    assert published.status_code == 200
    published_ids = {item["schedule_id"] for item in published.json()["schedules"]}
    assert {first["schedule_id"], second["schedule_id"]}.issubset(published_ids)



def test_dispatcher_does_not_report_late_confirmation_after_recovery_quarantine() -> None:
    client = authenticated_client()
    schedule = _scheduled_due_post(client)
    database_path = get_settings().database_path

    class LateConfirmingAdapter:
        def publish(self, draft: dict[str, object], *, idempotency_key: str) -> PublishReceipt:
            # Simulate stale-worker recovery winning while the provider request
            # is still in flight. A late response must not overwrite quarantine.
            with TaskRepository(database_path)._connection() as connection:
                cursor = connection.execute(
                    """
                    UPDATE content_publish_schedules
                    SET status = 'unknown_outcome',
                        last_error_code = 'worker_interrupted',
                        updated_at = ?
                    WHERE schedule_id = ? AND status = 'publishing'
                    """,
                    (datetime.now(UTC).isoformat(), schedule["schedule_id"]),
                )
                assert cursor.rowcount == 1
            return PublishReceipt(provider_post_id="late-provider-confirmation")

    dispatcher = ContentScheduleDispatcher(
        database_path, adapters={"telegram": LateConfirmingAdapter()}
    )

    result = dispatcher.run_once()

    assert result == {
        "schedule_id": schedule["schedule_id"],
        "status": "unknown_outcome",
        "reason_code": "schedule_state_changed_before_confirmation_commit",
    }
    with TaskRepository(database_path)._connection() as connection:
        stored = connection.execute(
            """
            SELECT status, provider_post_id, published_at
            FROM content_publish_schedules WHERE schedule_id = ?
            """,
            (schedule["schedule_id"],),
        ).fetchone()
    assert stored is not None
    assert stored["status"] == "unknown_outcome"
    assert stored["provider_post_id"] is None
    assert stored["published_at"] is None
