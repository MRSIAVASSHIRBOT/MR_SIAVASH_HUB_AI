from __future__ import annotations

import pytest

from mrhub.agents.capability_gaps import (
    CapabilityGapReport,
    evaluate_capability_gaps,
    evaluate_registered_tool_gaps,
)


def test_capability_gap_matching_uses_exact_registered_names_not_descriptions():
    report = evaluate_capability_gaps(
        ["Text.Echo", "video.generate"],
        [
            {
                "name": "text.echo",
                "description": "A tool that can also mention video.generate",
            }
        ],
    )

    assert isinstance(report, CapabilityGapReport)
    assert report.required == ("Text.Echo", "video.generate")
    assert report.available == ("Text.Echo",)
    assert report.missing == ("video.generate",)
    assert report.complete is False


def test_capability_gap_matching_is_case_insensitive_and_preserves_requirement_order():
    report = evaluate_capability_gaps(
        ["video.generate", "text.echo"],
        [
            {"name": "TEXT.ECHO", "description": "echo"},
            {"name": "Video.Generate", "description": "video"},
        ],
    )

    assert report.available == ("video.generate", "text.echo")
    assert report.missing == ()
    assert report.complete is True
    assert report.as_dict() == {
        "required": ["video.generate", "text.echo"],
        "available": ["video.generate", "text.echo"],
        "missing": [],
        "complete": True,
    }


def test_capability_gap_matching_deduplicates_requirements_without_reordering():
    report = evaluate_capability_gaps(
        ["text.echo", "TEXT.ECHO", "video.generate"],
        [{"name": "text.echo", "description": "echo"}],
    )

    assert report.required == ("text.echo", "video.generate")
    assert report.available == ("text.echo",)
    assert report.missing == ("video.generate",)


def test_registered_tool_gap_evaluator_uses_only_server_catalog_names():
    class ServerOwnedRegistry:
        def catalog(self):
            return [
                {"name": "content.publish", "description": "Can also inspect devices"},
            ]

    report = evaluate_registered_tool_gaps(
        ["content.publish", "device.inspect"],
        ServerOwnedRegistry(),  # type: ignore[arg-type]
    )

    assert report.available == ("content.publish",)
    assert report.missing == ("device.inspect",)


@pytest.mark.parametrize(
    ("required", "catalog", "error"),
    [
        ("text.echo", [], TypeError),
        ({"text.echo": True}, [], TypeError),
        ([" "], [], ValueError),
        (["x" * 81], [], ValueError),
        ([1], [], TypeError),
        (["text.echo"], ["not-a-mapping"], TypeError),
        (["text.echo"], [{"name": " "}], ValueError),
        (["text.echo"], [{"name": "x" * 81}], ValueError),
    ],
)
def test_capability_gap_evaluator_rejects_invalid_inputs(required, catalog, error):
    with pytest.raises(error):
        evaluate_capability_gaps(required, catalog)


def test_capability_gap_evaluator_enforces_catalog_and_requirement_bounds():
    with pytest.raises(ValueError, match="Too many required capabilities"):
        evaluate_capability_gaps(
            [f"capability.{index}" for index in range(51)],
            [],
        )

    with pytest.raises(ValueError, match="catalog exceeds"):
        evaluate_capability_gaps(
            ["capability.0"],
            [{"name": f"capability.{index}"} for index in range(201)],
        )
