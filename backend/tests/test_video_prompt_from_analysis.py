import pytest

from mrhub.video_intelligence.prompt_from_analysis import (
    AnalysisPromptOptions,
    PromptCompositionUnavailable,
    compose_prompts_from_analysis,
)


def _analysis_result(scene_starts):
    technical = {
        "asset_id": "asset-1",
        "analysis_window_seconds": 5.0,
    }
    if scene_starts is not None:
        technical["scene_start_timestamps"] = scene_starts
    technical["scene_boundaries_truncated"] = scene_starts is not None
    return {
        "semantic_visual_analysis": {
            "status": "completed",
            "assets": [
                {
                    "asset_id": "asset-1",
                    "status": "completed",
                    "style_summary": "A restrained original visual sequence.",
                    "observations": [
                        {
                            "timestamp_seconds": 0.5,
                            "description": "A wide view of an original geometric subject.",
                            "confidence": 0.9,
                        },
                        {
                            "timestamp_seconds": 3.0,
                            "description": "A closer view with soft directional light.",
                            "confidence": 0.8,
                        },
                    ],
                }
            ],
        },
        "assets": [technical],
    }


def test_prompt_composition_uses_scene_cuts_as_per_beat_timing_cues():
    prompts = compose_prompts_from_analysis(
        _analysis_result([0.0, 2.0, 3.0, 4.0]),
        AnalysisPromptOptions(),
    )

    assert len(prompts) == 1
    result = prompts[0]
    assert result["scene_cut_count"] == 3
    assert result["scene_boundaries_truncated"] is True
    assert result["timeline"] == [
        {
            "start_seconds": 0.5,
            "end_seconds": 3.0,
            "source_timestamp_seconds": 0.5,
            "scene_cut_timestamps": [2.0, 3.0],
        },
        {
            "start_seconds": 3.0,
            "end_seconds": 5.0,
            "source_timestamp_seconds": 3.0,
            "scene_cut_timestamps": [3.0, 4.0],
        },
    ]
    assert "2.000s" in result["prompt"]
    assert "4.000s" in result["prompt"]
    assert "approximate pacing cues" in result["prompt"]


@pytest.mark.parametrize(
    "scene_starts",
    [
        [0.0, 2.0, 1.0],
        [0.0, 5.0],
        [0.1, 2.0],
        [0.0, True],
        [0.0, 10**400],
        "not-a-list",
        [0.0] + [float(index) for index in range(1, 26)],
    ],
)
def test_prompt_composition_rejects_malformed_scene_boundaries(scene_starts):
    with pytest.raises(PromptCompositionUnavailable) as error:
        compose_prompts_from_analysis(
            _analysis_result(scene_starts),
            AnalysisPromptOptions(),
        )
    assert error.value.code == "analysis_result_invalid"


def test_prompt_composition_supports_legacy_analysis_without_scene_boundaries():
    prompts = compose_prompts_from_analysis(
        _analysis_result(None),
        AnalysisPromptOptions(),
    )

    assert prompts[0]["scene_cut_count"] == 0
    assert prompts[0]["scene_boundaries_truncated"] is False
    assert all("scene_cut_timestamps" not in item for item in prompts[0]["timeline"])



def _storyboard_draft(draft_id):
    return {
        "draft_id": str(draft_id),
        "analysis_id": "analysis-1",
        "asset_id": "asset-1",
        "duration_seconds": 8,
        "aspect_ratio": "16:9",
        "version": 4,
        "beats": [
            {
                "start_seconds": 0.0,
                "end_seconds": 3.0,
                "generation_instruction": "Create a custom original opening beat",
                "transition_to_next": "soft light wipe",
                "source_timestamp_seconds": 1.0,
                "confidence": 0.7,
            },
            {
                "start_seconds": 3.0,
                "end_seconds": 8.0,
                "generation_instruction": "Resolve with a clear final product frame",
                "transition_to_next": "hold",
                "source_timestamp_seconds": 3.5,
                "confidence": 0.95,
            },
        ],
    }


def test_prompt_composition_uses_versioned_storyboard_for_its_asset():
    from uuid import UUID

    draft_id = UUID("33333333-3333-4333-8333-333333333333")
    draft = _storyboard_draft(draft_id)
    options = AnalysisPromptOptions(timeline_draft_id=draft_id, timeline_draft_version=4)

    prompts = compose_prompts_from_analysis(
        _analysis_result([0.0, 2.0, 3.0, 4.0]),
        options,
        timeline_draft=draft,
    )

    assert len(prompts) == 1
    result = prompts[0]
    assert "custom original opening beat" in result["prompt"]
    assert "8-second video in 16:9 aspect ratio" in result["prompt"]
    assert result["duration_seconds"] == 8
    assert result["aspect_ratio"] == "16:9"
    assert result["timeline_draft_id"] == str(draft_id)
    assert result["timeline_draft_version"] == 4
    assert result["beats"][0]["confidence"] == 0.7
    assert result["timeline"] == [
        {
            "start_seconds": 0.0,
            "end_seconds": 3.0,
            "source_timestamp_seconds": 1.0,
            "confidence": 0.7,
            "scene_cut_timestamps": [2.0, 3.0],
        },
        {
            "start_seconds": 3.0,
            "end_seconds": 8.0,
            "source_timestamp_seconds": 3.5,
            "confidence": 0.95,
            "scene_cut_timestamps": [4.0],
        },
    ]


def test_prompt_composition_requires_matching_draft_identity():
    from uuid import UUID

    draft_id = UUID("33333333-3333-4333-8333-333333333333")
    with pytest.raises(PromptCompositionUnavailable) as missing:
        compose_prompts_from_analysis(
            _analysis_result([0.0, 2.0]),
            AnalysisPromptOptions(timeline_draft_id=draft_id, timeline_draft_version=4),
        )
    assert missing.value.code == "timeline_draft_unavailable"

    draft = _storyboard_draft(draft_id)
    draft["draft_id"] = "44444444-4444-4444-8444-444444444444"
    with pytest.raises(PromptCompositionUnavailable) as mismatch:
        compose_prompts_from_analysis(
            _analysis_result([0.0, 2.0]),
            AnalysisPromptOptions(timeline_draft_id=draft_id, timeline_draft_version=4),
            timeline_draft=draft,
        )
    assert mismatch.value.code == "timeline_draft_invalid"


def test_prompt_composition_rejects_storyboard_for_an_unrelated_asset():
    from uuid import UUID

    draft_id = UUID("33333333-3333-4333-8333-333333333333")
    draft = _storyboard_draft(draft_id)
    draft["asset_id"] = "asset-not-in-analysis"
    with pytest.raises(PromptCompositionUnavailable) as error:
        compose_prompts_from_analysis(
            _analysis_result([0.0, 2.0]),
            AnalysisPromptOptions(timeline_draft_id=draft_id, timeline_draft_version=4),
            timeline_draft=draft,
        )
    assert error.value.code == "timeline_draft_invalid"



def test_prompt_composition_requires_the_exact_storyboard_version():
    from uuid import UUID

    from pydantic import ValidationError

    draft_id = UUID("33333333-3333-4333-8333-333333333333")
    with pytest.raises(ValidationError):
        AnalysisPromptOptions(timeline_draft_id=draft_id)
    with pytest.raises(ValidationError):
        AnalysisPromptOptions(timeline_draft_id=draft_id, timeline_draft_version=True)

    with pytest.raises(PromptCompositionUnavailable) as error:
        compose_prompts_from_analysis(
            _analysis_result([0.0, 2.0]),
            AnalysisPromptOptions(
                timeline_draft_id=draft_id,
                timeline_draft_version=5,
            ),
            timeline_draft=_storyboard_draft(draft_id),
        )
    assert error.value.code == "timeline_draft_version_conflict"



def test_prompt_composition_rejects_storyboard_source_timestamp_outside_analysis_window():
    from uuid import UUID

    draft_id = UUID("33333333-3333-4333-8333-333333333333")
    draft = _storyboard_draft(draft_id)
    draft["beats"][1]["source_timestamp_seconds"] = 5.0

    with pytest.raises(PromptCompositionUnavailable) as error:
        compose_prompts_from_analysis(
            _analysis_result([0.0, 2.0, 3.0, 4.0]),
            AnalysisPromptOptions(
                timeline_draft_id=draft_id,
                timeline_draft_version=4,
            ),
            timeline_draft=draft,
        )

    assert error.value.code == "timeline_draft_invalid"
