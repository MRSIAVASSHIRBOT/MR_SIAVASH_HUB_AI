from mrhub.diagnostics.model_recommender import recommend_model_profiles


def test_recommender_deduplicates_profiles_and_never_runs_models():
    result = recommend_model_profiles(
        {"memory": {"available_gib": 12}},
        ["small-text-cpu-example", "small-text-cpu-example"],
    )
    assert result["count"] == 1
    assert result["best_candidate_profile_id"] is None
    assert result["decision_mode"] == "advisory_only"
    assert result["starts_inference"] is False
    assert result["downloads_model"] is False
    assert result["selects_provider"] is False


def test_recommender_does_not_guess_when_hardware_data_is_missing():
    result = recommend_model_profiles(
        {},
        ["small-text-cpu-example", "gpu-model-example"],
    )
    assert result["best_candidate_profile_id"] is None
    assert all(item["assessment"]["status"] == "insufficient_data" for item in result["results"])


def test_recommender_keeps_gpu_profiles_out_of_candidate_list_even_with_ram():
    result = recommend_model_profiles(
        {"memory": {"available_gib": 64}, "gpu": {"status": "not_measured"}},
        ["gpu-model-example"],
    )
    assert result["best_candidate_profile_id"] is None
    assert result["results"][0]["recommendation"] == "not_recommended_or_unverified"
    assert result["results"][0]["assessment"]["status"] == "insufficient_data"


def test_recommender_rejects_unknown_profile_ids():
    try:
        recommend_model_profiles({"memory": {"available_gib": 12}}, ["unknown-profile"])
    except KeyError as exc:
        assert list(exc.args[0]) == ["unknown-profile"]
    else:
        raise AssertionError("Unknown profile ID should be rejected")


def test_recommender_enforces_profile_count_limit():
    try:
        recommend_model_profiles(
            {"memory": {"available_gib": 12}},
            ["small-text-cpu-example"] * 21,
        )
    except ValueError as exc:
        assert "20" in str(exc)
    else:
        raise AssertionError("More than 20 profile IDs should be rejected")



def test_recommender_only_promotes_verified_resource_fit_profiles(monkeypatch):
    from mrhub.diagnostics import model_recommender

    monkeypatch.setattr(
        model_recommender,
        "get_model_profile",
        lambda _profile_id: {
            "id": "verified-cpu-profile",
            "name": "Verified CPU model",
            "minimum_ram_gib": 4.0,
            "recommended_ram_gib": 8.0,
            "requires_gpu": False,
            "source_kind": "vendor_documentation",
            "verified": True,
            "notes": "Test fixture",
        },
    )

    result = model_recommender.recommend_model_profiles(
        {"memory": {"available_gib": 12}},
        ["verified-cpu-profile"],
    )

    assert result["best_candidate_profile_id"] == "verified-cpu-profile"
    assert result["results"][0]["recommendation"] == "candidate"
    assert result["results"][0]["verified"] is True


def test_recommender_labels_unverified_fit_separately_from_insufficient_data():
    result = recommend_model_profiles(
        {"memory": {"available_gib": 12}},
        ["small-text-cpu-example", "gpu-model-example"],
    )

    by_id = {item["profile_id"]: item for item in result["results"]}
    assert by_id["small-text-cpu-example"]["assessment"]["status"] == "likely_fit"
    assert by_id["small-text-cpu-example"]["recommendation"] == "unverified_estimate"
    assert by_id["gpu-model-example"]["recommendation"] == "insufficient_data"
    assert result["best_candidate_profile_id"] is None
