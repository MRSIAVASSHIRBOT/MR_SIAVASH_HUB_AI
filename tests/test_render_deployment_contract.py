from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_render_supervisor_starts_and_stops_all_runtime_processes():
    script = (ROOT / "scripts" / "start-render.sh").read_text(encoding="utf-8")

    assert "python -m mrhub.worker_service &" in script
    assert 'python -m uvicorn mrhub.main:app --host "$MRH_HOST" --port "$MRH_PORT" &' in script
    assert "python -m el_ai &" in script
    assert 'wait -n "$API_PID" "$WORKER_PID" "$EL_AI_PID"' in script
    assert 'kill -TERM "$API_PID" "$WORKER_PID" "$EL_AI_PID"' in script
    assert 'STATUS=1' in script
    assert 'trap shutdown TERM INT EXIT' in script


def test_render_blueprint_keeps_secrets_private_and_public_bot_disabled():
    blueprint = (ROOT / "render.yaml").read_text(encoding="utf-8")

    for key in (
        "MRH_WORKFLOW_PAYLOAD_KEY",
        "MRH_OWNER_SETUP_TOKEN",
        "EL_AI_CREDENTIAL_ENCRYPTION_KEY",
        "TELEGRAM_BRIDGE_SHARED_SECRET",
        "TELEGRAM_OWNER_IDS",
    ):
        assert f"key: {key}\n        sync: false" in blueprint

    assert "TELEGRAM_TRANSPORT" in blueprint
    assert "value: cloudflare_bridge" in blueprint
    assert "TELEGRAM_PUBLIC_ENABLED" in blueprint
    assert 'value: "false"' in blueprint
    assert "EL_AI_CREDENTIAL_STORE" in blueprint
    assert "value: encrypted_file" in blueprint
    assert "@e8cb136c22ba5a343cb5725763b23cadb47f55de" in blueprint
