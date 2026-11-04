from uuid import UUID

import pytest
from pydantic import ValidationError

from mrhub.video_intelligence.prompt_from_analysis import (
    AnalysisPromptOptions,
    PromptCompositionUnavailable,
    compose_prompts_from_analysis,
)

ASSET_ID = "22222222-2222-4222-8222-222222222222"
DRAFT_ID = "33333333-3333-4333-8333-333333333333"


def _analysis_result():
    return {
        "assets": [
            {
                "asset_id": ASSET_ID,
                "analysis_window_seconds": 10.0,
                "scene_start_timestamps": [0.0, 4.0],
                "scene_boundaries_truncated": False,
            }
        ],
        "semantic_visual_analysis": {
            "status": "completed",
            "assets": [
                {
                    "asset_id": ASSET_ID,
                    "status": "completed",
                    "style_summary": "Original cinematic product imagery",
                    "observations": [
                        {
                            "timestamp_seconds": 0.0,
                            "description": "A geometric object on a dark background",
                            "shot_scale": "wide",
                            "camera_movement": "static",
                            "composition": "Centered",
                            "lighting": "Soft rim light",
                            "color_notes": ["emerald"],
                            "confidence": 0.9,
                        }
                    ],
                }
            ],
        },
    }


def _draft():
    return {
        "draft_id": DRAFT_ID,
        "analysis_id": "11111111-1111-4111-8111-111111111111",
        "asset_id": ASSET_ID,
        "duration_seconds": 8,
        "aspect_ratio": "16:9",
        "version": 3,
        "beats": [
            {
                "start_seconds": 0.0,
                "end_seconds": 3.0,
                "generation_instruction": "Open with a slow reveal of an original object",
                "transition_to_next": "match cut",
                "source_timestamp_seconds": 0.5,
                "confidence": 0.9,
            },
            {
                "start_seconds": 3.0,
                "end_seconds": 8.0,
                "generation_instruction": "Move to a close detail shot",
                "transition_to_next": "clean cut",
                "source_timestamp_seconds": 4.5,
                "confidence": 0.8,
            },
        ],
    }


def test_saved_storyboard_overrides_analysis_beats_without_execution():
    options = AnalysisPromptOptions(
        draft_id=UUID(DRAFT_ID),
        expected_draft_version=3,
        brand_name="MR_SIAVASH_IR_BOT",
    )

    prompts = compose_prompts_from_analysis(
        _analysis_result(), options, draft_override=_draft()
    )

    assert len(prompts) == 1
    prompt = prompts[0]
    assert prompt["draft_id"] == DRAFT_ID
    assert prompt["draft_version"] == 3
    assert prompt["duration_seconds"] == 8
    assert prompt["beat_count"] == 2
    assert prompt["timeline"][0]["source_timestamp_seconds"] == 0.5
    assert "slow reveal of an original object" in prompt["prompt"]
    assert "close detail shot" in prompt["prompt"]
    assert "MR_SIAVASH_IR_BOT" in prompt["prompt"]


def test_saved_storyboard_rejects_draft_for_asset_outside_analysis():
    draft = _draft()
    draft["asset_id"] = "44444444-4444-4444-8444-444444444444"

    with pytest.raises(PromptCompositionUnavailable) as error:
        compose_prompts_from_analysis(
            _analysis_result(), AnalysisPromptOptions(), draft_override=draft
        )

    assert error.value.code == "timeline_draft_asset_mismatch"


def test_prompt_options_require_draft_id_and_expected_version_together():
    with pytest.raises(ValidationError):
        AnalysisPromptOptions(draft_id=UUID(DRAFT_ID))

    with pytest.raises(ValidationError):
        AnalysisPromptOptions(expected_draft_version=1)
