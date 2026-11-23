from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_render_supervisor_starts_and_stops_only_hub_processes():
    script = (ROOT / "scripts" / "start-render.sh").read_text(encoding="utf-8")

    assert "python -m mrhub.worker_service &" in script
    assert 'python -m uvicorn mrhub.main:app --host "$MRH_HOST" --port "$MRH_PORT" &' in script
    assert 'wait -n "$API_PID" "$WORKER_PID"' in script
    assert 'kill -TERM "$API_PID" "$WORKER_PID"' in script
    assert "python -m el_ai" not in script
    assert "EL_AI_PID" not in script
    assert "STATUS=1" in script
    assert "trap shutdown TERM INT EXIT" in script


def test_render_blueprint_separates_hub_and_el_ai_runtime_boundaries():
    blueprint = (ROOT / "render.yaml").read_text(encoding="utf-8")
    assert "name: mr-siavash-hub-ai" in blueprint
    assert "name: mr-siavash-el-ai-bridge" in blueprint
    assert "type: worker" in blueprint
    assert "repo: https://github.com/MRSIAVASSHIRBOT/MR_SIAVASH_EL_AI.git" in blueprint
    assert "branch: main" in blueprint
    assert "property: hostport" in blueprint
    assert "HUB_ALLOW_RENDER_PRIVATE_NETWORK" in blueprint
    assert 'value: "true"' in blueprint
    assert blueprint.count('autoDeployTrigger: "off"') == 2
    assert "autoDeploy: true" not in blueprint
    assert "mountPath: /var/data" in blueprint

    hub, bridge = blueprint.split("  - type: worker", 1)
    worker_build = bridge.split("    startCommand:", 1)[0]
    install_marker = "MRSIAVASSHIRBOT/MR_SIAVASH_EL_AI.git@"
    assert worker_build.count(install_marker) == 1
    pinned_commit = worker_build.split(install_marker, 1)[1].split('"', 1)[0]
    assert len(pinned_commit) == 40
    assert all(character in "0123456789abcdef" for character in pinned_commit), (
        "EL_AI worker must install a reviewed immutable commit, never a moving branch"
    )
    assert "pip install ." not in worker_build
    assert "MR_SIAVASSHIRBOT/MR_SIAVASH_HUB_AI.git" not in worker_build

    for hub_secret in ("MRH_WORKFLOW_PAYLOAD_KEY", "MRH_OWNER_SETUP_TOKEN"):
        assert f"key: {hub_secret}\n        sync: false" in hub
        assert hub_secret not in bridge

    for bridge_secret in (
        "EL_AI_CREDENTIAL_ENCRYPTION_KEY",
        "TELEGRAM_BRIDGE_SHARED_SECRET",
        "TELEGRAM_OWNER_IDS",
    ):
        assert f"key: {bridge_secret}\n        sync: false" in bridge
        assert bridge_secret not in hub

    assert "TELEGRAM_TRANSPORT" not in hub
    assert "EL_AI_STATE_DIR" not in hub
    assert "MRH_DATABASE_PATH" not in bridge
    assert "MRH_WORKFLOW_PAYLOAD_KEY" not in bridge
    assert "MRH_OWNER_SETUP_TOKEN" not in bridge
    assert 'value: "false"' in bridge
    assert "plan: starter" in hub
    assert "plan: starter" in bridge


def test_render_deployment_docs_require_blueprint_auto_sync_to_remain_disabled():
    docs = (ROOT / "docs" / "operations" / "render-deployment.md").read_text(
        encoding="utf-8"
    )

    assert "Blueprint **Auto Sync** is a separate workspace setting" in docs
    assert "must also remain disabled" in docs
