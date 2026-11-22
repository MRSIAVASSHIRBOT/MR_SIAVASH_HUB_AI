from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def test_render_services_require_explicit_manual_deployment() -> None:
    blueprint = (REPOSITORY_ROOT / "render.yaml").read_text(encoding="utf-8")
    lines = blueprint.splitlines()
    service_starts = [
        index for index, line in enumerate(lines) if line.startswith("  - type:")
    ]

    assert service_starts, "render.yaml must declare at least one service"

    for index, start in enumerate(service_starts):
        end = service_starts[index + 1] if index + 1 < len(service_starts) else len(lines)
        settings = {line.strip() for line in lines[start:end]}
        assert 'autoDeployTrigger: "off"' in settings, (
            "Every Render service must explicitly disable automatic deployment"
        )
        assert "autoDeploy: true" not in settings, (
            "Legacy autoDeploy=true can trigger an unattended paid deployment"
        )
