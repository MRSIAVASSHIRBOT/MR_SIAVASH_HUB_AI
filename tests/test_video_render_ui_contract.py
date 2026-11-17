from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_render_dashboard_explains_source_audio_and_shows_verified_output_metadata():
    app = (ROOT / "backend/mrhub/web/app.js").read_text(encoding="utf-8")
    page = (ROOT / "backend/mrhub/web/index.html").read_text(encoding="utf-8")

    assert "render.output_metadata" in app
    assert "ترک صوتی منبع موجود است" in app
    assert "صدای اصلیِ تأییدشده" in page
    assert "وضعیت نامعلوم" in page
    assert "video-render-preflight" in page
    assert "video-render-preflight-result" in page
    assert "render-preflight" in app
    assert "هیچ رندر یا Providerی اجرا نمی‌شود" in app
