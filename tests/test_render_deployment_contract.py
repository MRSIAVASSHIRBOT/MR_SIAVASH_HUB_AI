import re
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def test_render_services_require_explicit_manual_deployment() -> None:
    blueprint = (REPOSITORY_ROOT / "render.yaml").read_text(encoding="utf-8")
    services_section = blueprint.partition("services:")[2]
    service_blocks = re.split(r"(?m)^  - type:\\s*", services_section)
    service_blocks = [block for block in service_blocks if block.strip()]

    assert service_blocks, "render.yaml must declare at least one service"

    for service in service_blocks:
        trigger = re.search(
            r"(?m)^    autoDeployTrigger:\\s*([^#\\s]+)\\s*$",
            service,
        )
        assert trigger is not None, (
            "Every Render service must explicitly disable automatic deployment"
        )
        assert trigger.group(1).strip("\\"'") == "off"
        assert not re.search(
            r"(?mi)^    autoDeploy:\\s*true\\s*$",
            service,
        ), "Legacy autoDeploy=true can trigger an unattended paid deployment"
