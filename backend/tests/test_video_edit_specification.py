import pytest
from pydantic import ValidationError

from mrhub.video_intelligence.edit_spec import build_edit_specification
from mrhub.video_intelligence.schemas import AnalysisMode, BrandIdentity, VideoAnalysisRequest


def _asset_result():
    return {
        "asset_id": "asset-123",
        "technical_metadata": {"metadata_status": "available"},
        "analysis_window_seconds": 12.0,
        "scene_start_timestamps": [0.0, 3.5, 8.0],
        "scene_boundaries_truncated": False,
        "semantic_visual_analysis": {
            "status": "completed",
            "style_summary": "Measured cinematic framing with soft directional light.",
            "observations": [
                {"timestamp_seconds": 0.0, "description": "Wide opening frame."}
            ],
        },
    }


def test_faithful_edit_spec_preserves_reference_and_prepares_brand_guidance():
    request = VideoAnalysisRequest(
        mode=AnalysisMode.FAITHFUL,
        source_asset_ids=["asset-123"],
        duration_seconds=12,
        output_aspect_ratio="16:9",
        include_audio_analysis=False,
        brand=BrandIdentity(
            brand_name="Example Studio",
            handle="@example",
            logo_asset_id="logo-123",
            colors=["emerald", "charcoal"],
            font_preferences=["Vazirmatn"],
            tone="Precise and educational",
        ),
        custom_changes={"captions": "Persian captions, high contrast"},
    )

    specification = build_edit_specification(request, [_asset_result()])

    assert specification.style_strategy == "preserve_reference"
    assert specification.output_aspect_ratio == "16:9"
    assert specification.requested_output_duration_seconds == 12
    assert specification.sources[0].scene_start_timestamps == [0.0, 3.5, 8.0]
    assert specification.sources[0].visual_style_summary.startswith("Measured cinematic")
    assert specification.brand_guidance.status == "guidance_prepared"
    assert specification.brand_guidance.logo_asset_id == "logo-123"
    assert specification.custom_edit_guidance.directives["captions"].startswith("Persian")
    assert specification.audio_plan_status == "not_requested"
    assert specification.timeline_status == "scene_map_prepared_timeline_not_built"
    assert specification.render_status == "not_implemented"


def test_fusion_edit_spec_marks_reference_plus_user_direction():
    request = VideoAnalysisRequest(
        mode=AnalysisMode.FUSION,
        source_asset_ids=["asset-123"],
        include_audio_analysis=True,
    )

    specification = build_edit_specification(request, [_asset_result()])

    assert specification.style_strategy == "reference_plus_user_direction"
    assert specification.brand_guidance.status == "not_provided"
    assert specification.custom_edit_guidance.status == "none"
    assert specification.audio_plan_status == "requested_not_implemented"


def test_edit_spec_rejects_scene_map_without_zero_or_with_out_of_range_boundary():
    request = VideoAnalysisRequest(
        mode=AnalysisMode.FAITHFUL,
        source_asset_ids=["asset-123"],
    )
    invalid = _asset_result()
    invalid["scene_start_timestamps"] = [1.0, 3.5, 8.0]

    with pytest.raises(ValidationError):
        build_edit_specification(request, [invalid])


def test_request_bounds_custom_directive_keys_and_values():
    with pytest.raises(ValidationError):
        VideoAnalysisRequest(
            mode=AnalysisMode.FAITHFUL,
            source_asset_ids=["asset-123"],
            custom_changes={"x" * 65: "value"},
        )

    with pytest.raises(ValidationError):
        VideoAnalysisRequest(
            mode=AnalysisMode.FAITHFUL,
            source_asset_ids=["asset-123"],
            custom_changes={"captions": "x" * 501},
        )
