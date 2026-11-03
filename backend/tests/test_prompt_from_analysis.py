from uuid import UUID

import pytest
from fastapi import HTTPException

from mrhub.api.routes import video_intelligence as video_route
from mrhub.security.auth import AuthenticatedUser
from mrhub.video_intelligence.prompt_from_analysis import (
    AnalysisPromptOptions,
    PromptCompositionUnavailable,
    compose_prompts_from_analysis,
)


def _observation(timestamp, description):
    return {
        "timestamp_seconds": timestamp,
        "description": description,
        "shot_scale": "wide",
        "camera_movement": "static",
        "composition": "Centered subject and negative space.",
        "lighting": "Soft directional light.",
        "color_notes": ["emerald", "charcoal"],
        "confidence": 0.9,
    }


def _analysis_result():
    return {
        "mode": "faithful_style_reconstruction",
        "analysis_level": "bounded_technical_temporal_and_local_semantic",
        "assets": [
            {"asset_id": "asset-a", "analysis_window_seconds": 4.5},
            {"asset_id": "asset-b", "analysis_window_seconds": 6.0},
        ],
        "semantic_visual_analysis": {
            "status": "completed",
            "assets": [
                {
                    "asset_id": "asset-a",
                    "status": "completed",
                    "style_summary": "Restrained cinematic lighting and balanced framing.",
                    "observations": [
                        _observation(0.0, "A wide opening view."),
                        _observation(1.5, "The subject is framed closer."),
                    ],
                },
                {
                    "asset_id": "asset-b",
                    "status": "completed",
                    "style_summary": "Clean studio product lighting.",
                    "observations": [
                        _observation(0.0, "A product silhouette against a plain background."),
                        _observation(3.0, "A closer product view with directional highlights."),
                    ],
                },
            ],
        },
    }


def test_compose_prompts_from_analysis_returns_independent_evidence_linked_prompts():
    prompts = compose_prompts_from_analysis(
        _analysis_result(),
        AnalysisPromptOptions(
            aspect_ratio="9:16",
            brand_name="MR_SIAVASH_IR_BOT",
            colors=["#071A12", "#00C878"],
        ),
    )

    assert len(prompts) == 2
    assert [item["asset_id"] for item in prompts] == ["asset-a", "asset-b"]
    assert prompts[0]["duration_seconds"] == 5
    assert prompts[0]["beat_count"] == 2
    assert prompts[0]["timeline"] == [
        {
            "start_seconds": 0.0,
            "end_seconds": 1.5,
            "source_timestamp_seconds": 0.0,
        },
        {
            "start_seconds": 1.5,
            "end_seconds": 5.0,
            "source_timestamp_seconds": 1.5,
        },
    ]
    assert "sampled frame at 1.500s" in prompts[0]["prompt"]
    assert "MR_SIAVASH_IR_BOT" in prompts[0]["prompt"]
    assert "Do not reproduce protected logos" in prompts[0]["prompt"]


def test_prompt_composition_refuses_missing_semantic_analysis():
    result = _analysis_result()
    result["semantic_visual_analysis"]["status"] = "not_configured"
    with pytest.raises(PromptCompositionUnavailable) as error:
        compose_prompts_from_analysis(result, AnalysisPromptOptions())
    assert error.value.code == "semantic_analysis_unavailable"


def test_prompt_composition_refuses_mismatched_asset_sets():
    result = _analysis_result()
    result["semantic_visual_analysis"]["assets"].pop()
    with pytest.raises(PromptCompositionUnavailable) as error:
        compose_prompts_from_analysis(result, AnalysisPromptOptions())
    assert error.value.code == "analysis_result_invalid"


def test_prompt_composition_refuses_observation_after_analysis_window():
    result = _analysis_result()
    result["semantic_visual_analysis"]["assets"][0]["observations"][1]["timestamp_seconds"] = 4.5
    with pytest.raises(PromptCompositionUnavailable) as error:
        compose_prompts_from_analysis(result, AnalysisPromptOptions())
    assert error.value.code == "analysis_result_invalid"


def test_prompt_options_bound_individual_palette_values():
    with pytest.raises(ValueError):
        AnalysisPromptOptions(colors=["x" * 1000])



def test_analysis_prompt_endpoint_is_owner_scoped_and_does_not_execute(
    monkeypatch,
):
    analysis_id = UUID("8a83e1f0-5cc7-4b9e-aec8-cd2e0b4d6a1e")

    class FakeRepository:
        def get(self, owner_user_id, requested_id):
            assert owner_user_id == "owner-a"
            assert requested_id == analysis_id
            return {
                "analysis_id": str(analysis_id),
                "status": "completed",
                "result": _analysis_result(),
            }

    monkeypatch.setattr(video_route, "_analysis_jobs", lambda: FakeRepository())
    response = video_route.compose_prompt_from_analysis(
        analysis_id,
        AnalysisPromptOptions(),
        AuthenticatedUser(user_id="owner-a", username="owner-a"),
    )
    assert response["status"] == "composed"
    assert response["execution"] == "not_started"
    assert response["count"] == 2


def test_analysis_prompt_endpoint_returns_not_found_for_non_owner(monkeypatch):
    analysis_id = UUID("8a83e1f0-5cc7-4b9e-aec8-cd2e0b4d6a1e")

    class FakeRepository:
        def get(self, owner_user_id, requested_id):
            assert owner_user_id == "owner-b"

    monkeypatch.setattr(video_route, "_analysis_jobs", lambda: FakeRepository())
    with pytest.raises(HTTPException) as error:
        video_route.compose_prompt_from_analysis(
            analysis_id,
            AnalysisPromptOptions(),
            AuthenticatedUser(user_id="owner-b", username="owner-b"),
        )
    assert error.value.status_code == 404


def test_analysis_prompt_endpoint_rejects_pending_analysis(monkeypatch):
    analysis_id = UUID("8a83e1f0-5cc7-4b9e-aec8-cd2e0b4d6a1e")

    class FakeRepository:
        def get(self, _owner_user_id, _requested_id):
            return {
                "analysis_id": str(analysis_id),
                "status": "running",
                "result": None,
            }

    monkeypatch.setattr(video_route, "_analysis_jobs", lambda: FakeRepository())
    with pytest.raises(HTTPException) as error:
        video_route.compose_prompt_from_analysis(
            analysis_id,
            AnalysisPromptOptions(),
            AuthenticatedUser(user_id="owner-a", username="owner-a"),
        )
    assert error.value.status_code == 409
