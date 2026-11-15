from types import SimpleNamespace

from mrhub.api.routes import telegram_integration
from mrhub.video_intelligence.generation_routing import GenerationRoutePreviewRequest


def test_telegram_video_route_preview_uses_shared_read_only_policy(monkeypatch):
    payload = GenerationRoutePreviewRequest(duration_seconds=10, aspect_ratio="9:16")
    expected = {
        "decision": {"selected": False, "reason": "no_compatible_provider"},
        "execution": "not_started",
        "provider_submission_started": False,
    }
    calls = {}

    def fake_preview(request):
        calls["payload"] = request
        return expected

    monkeypatch.setattr(telegram_integration, "preview_hybrid_route", fake_preview)
    result = telegram_integration.preview_telegram_video_route(
        payload,
        SimpleNamespace(client_id="client-1", owner_user_id="owner-1"),
    )

    assert result is expected
    assert calls["payload"] is payload


def test_pairing_challenge_accepts_explicit_video_read_scope():
    from uuid import uuid4

    payload = telegram_integration.PairingChallengeRequest(
        telegram_user_id=123456,
        client_id=uuid4(),
        label="EL_AI",
        scopes=["status:read", "video:read"],
    )
    assert payload.scopes == ["status:read", "video:read"]
