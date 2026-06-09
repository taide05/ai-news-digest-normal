def test_what_it_means_prompt_5_dimensions():
    from ai.analysis import build_what_it_means_prompt
    system, user = build_what_it_means_prompt(
        "GPT-5 was released today with benchmark improvements.",
        ["transformer", "llm"],
        ["agent", "reasoning"],
        ["AI agents are the future", "Scaling laws debate"]
    )
    assert "技术意义" in user
    assert "商业影响" in user
    assert "行业趋势" in user
    assert "反方观点" in user
    assert "与你相关" in user
    assert "GPT-5" in user
    assert "agent" in user
    assert "Scaling laws debate" in user


def test_what_it_means_prompt_empty_context():
    from ai.analysis import build_what_it_means_prompt
    system, user = build_what_it_means_prompt("Some article text.", [])
    assert "技术意义" in user
    assert "暂无记录" in user  # empty concepts


def test_what_it_means_prompt_backward_compat():
    """Calling without user_topics/read_titles should still work (default None)."""
    from ai.analysis import build_what_it_means_prompt
    system, user = build_what_it_means_prompt("Some article text.", ["llm"])
    assert "技术意义" in user
    assert "暂无记录" in user  # empty user_topics/read_titles
