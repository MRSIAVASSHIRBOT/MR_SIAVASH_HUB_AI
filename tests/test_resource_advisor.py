import pytest

from mrhub.diagnostics.resource_advisor import assess_model_resources


def profile(**overrides):
    values = {
        "name": "example-small-model",
        "minimum_ram_gib": 4,
        "recommended_ram_gib": 6,
        "requires_gpu": False,
    }
    values.update(overrides)
    return values


def report(available_gib=10):
    return {"memory": {"available_gib": available_gib}, "gpu": {"status": "not_measured"}}


def test_advisor_reports_likely_fit_after_system_reserve():
    result = assess_model_resources(report(10), profile())

    assert result["status"] == "likely_fit"
    assert result["usable_ram_gib"] == 8
    assert result["starts_inference"] is False


def test_advisor_distinguishes_tight_and_insufficient_ram():
    tight = assess_model_resources(report(7), profile())
    low = assess_model_resources(report(5), profile())

    assert tight["status"] == "likely_tight"
    assert low["status"] == "not_recommended"


def test_advisor_fails_closed_when_available_ram_is_missing():
    result = assess_model_resources({"memory": {}}, profile())

    assert result["status"] == "insufficient_data"
    assert result["starts_inference"] is False


def test_gpu_required_profile_is_unknown_without_vram_measurement():
    result = assess_model_resources(report(32), profile(requires_gpu=True))

    assert result["status"] == "insufficient_data"
    assert "GPU VRAM" in " ".join(result["reasons"])


def test_invalid_profile_is_rejected_without_running_inference():
    result = assess_model_resources(report(), profile(recommended_ram_gib=2))

    assert result["status"] == "invalid_profile"
    assert result["starts_inference"] is False


def test_negative_system_reserve_raises():
    with pytest.raises(ValueError):
        assess_model_resources(report(), profile(), system_reserve_gib=-1)
