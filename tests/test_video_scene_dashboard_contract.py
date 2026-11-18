from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_scene_analysis_dashboard_and_telegram_scope_are_explicit_and_opt_in():
    app = (ROOT / "backend/mrhub/web/app.js").read_text(encoding="utf-8")
    page = (ROOT / "backend/mrhub/web/index.html").read_text(encoding="utf-8")

    assert 'id="video-scene-job-form"' in page
    assert 'id="video-scene-asset"' in page
    assert 'id="video-scene-history-more"' in page
    assert "/video-intelligence/assets/" in app
    assert "/scene-jobs" in app
    assert "scene_start_times" in app
    assert "loadVideoSceneJobs(true)" in app
    assert "cancelVideoSceneJob(job.job_id)" in app
    assert "هیچ فایل یا Promptی به سرویس بیرونی ارسال نمی‌شود" in page

    analyze_scope = next(
        line for line in page.splitlines()
        if 'name="scopes"' in line and 'value="video:analyze"' in line
    )
    assert "checked" not in analyze_scope
    assert "تحلیل محلی صحنه‌ها" in page
