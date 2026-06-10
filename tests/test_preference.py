def test_compute_user_profile_cold_start(test_db, test_config):
    from ai.preference import compute_user_profile, invalidate_profile_cache
    invalidate_profile_cache()
    profile = compute_user_profile(test_db, test_config)
    assert profile["feedback_count"] == 0
    assert len(profile["topics"]) > 0
    assert "ai" in profile["topics"]


def test_compute_user_profile_cached(test_db, test_config):
    from ai.preference import compute_user_profile, invalidate_profile_cache
    invalidate_profile_cache()
    p1 = compute_user_profile(test_db, test_config)
    p2 = compute_user_profile(test_db, test_config)
    assert p1 is p2
