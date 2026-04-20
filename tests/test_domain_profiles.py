from research_mcp.domain_profiles import list_domain_profiles, resolve_domain_profile


def test_auto_profile_resolves_general_for_non_sbi_topic():
    resolution = resolve_domain_profile("auto", "causal inference robustness")

    assert resolution.requested_profile == "auto"
    assert resolution.resolved_profile.id == "general"
    assert resolution.profile_source == "auto"


def test_auto_profile_resolves_sbi_example_for_sbi_calibration_topic():
    resolution = resolve_domain_profile("auto", "calibration in simulation-based inference")

    assert resolution.requested_profile == "auto"
    assert resolution.resolved_profile.id == "sbi_calibration"
    assert resolution.resolved_profile.is_example is True
    assert resolution.profile_source == "auto"


def test_unknown_profile_falls_back_to_general():
    resolution = resolve_domain_profile("unknown", "anything")

    assert resolution.requested_profile == "unknown"
    assert resolution.resolved_profile.id == "general"
    assert resolution.profile_source == "fallback"


def test_list_domain_profiles_marks_sbi_as_example():
    profiles = list_domain_profiles()

    assert any(profile["id"] == "auto" for profile in profiles)
    assert any(profile["id"] == "general" and not profile["is_example"] for profile in profiles)
    assert any(profile["id"] == "sbi_calibration" and profile["is_example"] for profile in profiles)
