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
            "scene_cut_timestamps": [2.0],
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
    assert all(not item["scene_cut_timestamps"] for item in prompts[0]["timeline"])
