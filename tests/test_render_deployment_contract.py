from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def test_render_services_require_explicit_manual_deployment() -> None:
    blueprint = (REPOSITORY_ROOT / "render.yaml").read_text(encoding="utf-8")
    services_section = blueprint.partition("services:")[2]
    service_blocks = [
        block
        for block in services_section.split("\\n  - type:")[1:]
        if block.strip()
    ]

    assert service_blocks, "render.yaml must declare at least one service"

    for service in service_blocks:
        settings = {line.strip() for line in service.splitlines()}
        assert 'autoDeployTrigger: "off"' in settings, (
            "Every Render service must explicitly disable automatic deployment"
        )
        assert not any(
            line.lower() == "autodeploy: true" for line in settings
        ), "Legacy autoDeploy=true can trigger an unattended paid deployment"
