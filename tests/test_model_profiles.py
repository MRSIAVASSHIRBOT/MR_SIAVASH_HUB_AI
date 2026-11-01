from mrhub.diagnostics.model_profiles import get_model_profile, list_model_profiles


def test_profile_catalog_is_explicit_and_marks_estimates_unverified():
    profiles = list_model_profiles()

    assert {profile["id"] for profile in profiles} == {
        "small-text-cpu-example",
        "gpu-model-example",
    }
    assert all(profile["verified"] is False for profile in profiles)
    assert all(profile["source_kind"] == "operator_estimate" for profile in profiles)


def test_profile_catalog_returns_defensive_copies():
    profiles = list_model_profiles()
    profiles[0]["name"] = "mutated"

    assert get_model_profile("small-text-cpu-example")["name"] != "mutated"


def test_unknown_profile_returns_none():
    assert get_model_profile("not-a-real-profile") is None
