from pathlib import Path

WEB = Path(__file__).resolve().parents[1] / "backend" / "mrhub" / "web"


def test_agent_proposal_panel_exposes_bounded_owner_review_controls():
    html = (WEB / "index.html").read_text(encoding="utf-8")
    assert 'id="agent-proposal-form"' in html
    assert 'id="agent-proposal-tool-options"' in html
    assert 'maxlength="1200"' in html
    assert "تأیید ≠ فعال‌سازی" in html
    assert "عامل فعال نمی‌شود" in html


def test_agent_proposal_ui_uses_authenticated_owner_scoped_api_and_safe_text_rendering():
    script = (WEB / "app.js").read_text(encoding="utf-8")
    assert 'api("/tools")' in script
    assert 'api("/agent/proposals?limit=50")' in script
    assert 'api("/agent/proposals", { method: "POST", body: payload })' in script
    assert '"/review"' in script
    assert "fingerprint: record.fingerprint" in script
    assert "record.activation_state" in script
    assert 'element("button", "تأیید پیشنهاد (بدون فعال‌سازی)"' in script
    assert "container.append(label)" in script
    assert "innerHTML" not in script


def test_agent_proposal_controls_have_responsive_emerald_styles():
    css = (WEB / "app.css").read_text(encoding="utf-8")
    assert ".agent-proposal-tools" in css
    assert ".agent-proposal-tool-label" in css
    assert ".agent-proposal-card-actions" in css
    assert "var(--green)" in css
