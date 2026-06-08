from ai.analysis import (build_core_insight_prompt, build_what_it_means_prompt,
                            build_translation_prompt, build_concept_lookup_prompt,
                            build_review_prompt)


def test_core_insight_prompt_contains_article():
    sys_p, usr_p = build_core_insight_prompt("This is a test article about AI.")
    assert "This is a test article" in usr_p


def test_what_it_means_prompt_contains_concepts():
    sys_p, usr_p = build_what_it_means_prompt("test article", ["RLHF", "transformer"])
    assert "RLHF" in usr_p
    assert "transformer" in usr_p


def test_what_it_means_empty_concepts():
    sys_p, usr_p = build_what_it_means_prompt("test", [])
    assert "暂无记录" in usr_p


def test_translation_prompt_contains_full_text():
    sys_p, usr_p = build_translation_prompt("Hello world, this is AI news.")
    assert "Hello world" in usr_p


def test_concept_lookup_prompt_contains_term():
    sys_p, usr_p = build_concept_lookup_prompt("RLHF", "Some article context")
    assert "RLHF" in usr_p
    assert "Some article context" in usr_p


def test_review_prompt_contains_articles():
    articles = [{"title": "GPT-5 Released", "insight": "Big news"},
                {"title": "MoE Paper", "insight": "Efficient training"}]
    sys_p, usr_p = build_review_prompt(articles, ["RLHF"], ["LLMs"], ["frontend"])
    assert "GPT-5 Released" in usr_p
    assert "RLHF" in usr_p


def test_empty_review_data_handled():
    sys_p, usr_p = build_review_prompt([], [], [], [])
    assert "无" in usr_p or "暂无" in usr_p
